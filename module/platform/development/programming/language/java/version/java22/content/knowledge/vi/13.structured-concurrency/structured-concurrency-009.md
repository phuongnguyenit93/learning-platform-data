# Kết hợp ScopedValue để truyền ngữ cảnh trong cây tác vụ

## 1. Một request, nhiều tác vụ, cùng một ngữ cảnh

Một request có thể cần chạy đồng thời việc lấy hồ sơ, tra giá và kiểm tra tồn kho. Mỗi nhánh lại gọi qua nhiều lớp dịch vụ. Những dữ liệu như mã request, mã tenant và ngôn ngữ cần nhất quán trong toàn bộ quá trình, nhưng việc thêm chúng vào mọi chữ ký phương thức dễ làm chuỗi gọi trở nên dài và khó theo dõi.

`ScopedValue` cho phép một lớp mã ở đầu chuỗi gọi thiết lập ngữ cảnh để các phương thức phía dưới đọc. Khi kết hợp với `StructuredTaskScope`, cơ chế này còn truyền ngữ cảnh qua **cây tác vụ có cấu trúc**, gồm cả các nhánh con mở scope lồng nhau.

Hai API giải quyết hai phần liên quan:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ScopedValue` | Gắn dữ liệu ngữ cảnh với một khoảng thực thi và cung cấp cách đọc dữ liệu đó |
| `StructuredTaskScope` | Quản lý vòng đời nhóm tác vụ con, chờ kết quả và bảo đảm các luồng con kết thúc trước khi rời scope |
| Kết hợp cả hai | Cho phép tác vụ con kế thừa ràng buộc mà vẫn giữ vòng đời tác vụ nằm trong vòng đời ngữ cảnh |

Bài học thuộc module Java 22, nơi cả hai tính năng được cung cấp ở dạng preview. Những nguyên lý truyền ngữ cảnh theo cấu trúc vẫn còn hữu ích trong Java hiện đại. Để tránh hướng dẫn theo API preview cũ, **các chương trình trong bài dùng JDK 27**, theo tài liệu đối chiếu tại ngày 25/11/2026. `ScopedValue` đã là API chính thức từ Java 25; `StructuredTaskScope` trong JDK 27 vẫn là preview. Xem [API `ScopedValue`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html) và [API `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Khi dùng một JDK khác, cần chọn API reference và toolchain tương ứng. Không trộn constructor, lớp chính sách hoặc kiểu ngoại lệ của các lần preview trước vào chương trình dành cho JDK 27.

## 2. Thiết kế một ngữ cảnh chỉ đọc

Một ngữ cảnh nhỏ có thể được biểu diễn bằng record:

```java
private record RequestContext(
        String requestId,
        String tenantId,
        String language) {}

private static final ScopedValue<RequestContext> CONTEXT =
        ScopedValue.newInstance();
```

Ba chuỗi mô tả dữ liệu gắn với một request. Đối tượng `CONTEXT` là **khóa** để truy cập ngữ cảnh; nó không phải đối tượng ngữ cảnh của một request cụ thể.

Việc giữ khóa trong trường `private static final` có hai tác dụng:

- Các phương thức của lớp dùng chung đúng một đối tượng khóa.
- Mỗi request có thể bind một `RequestContext` khác nhau mà không thay khóa.

`static` ở đây không có nghĩa mọi thread đọc cùng một request. Giá trị đọc được phụ thuộc vào ràng buộc có hiệu lực trên thread đang thực thi.

Với ngữ cảnh bắt buộc, nên có một điểm đọc thể hiện rõ hợp đồng:

```java
private static RequestContext currentContext() {
    return CONTEXT.orElseThrow(() ->
            new IllegalStateException("request context is required"));
}
```

Nếu một phương thức cần ngữ cảnh nhưng chạy ngoài phạm vi hợp lệ, lỗi được phát hiện ngay. Không nên tự chọn một tenant hoặc request mặc định để che việc thiếu ngữ cảnh.

Ngữ cảnh dùng để truyền dữ liệu đầu vào chung theo chiều từ cha xuống con. Kết quả công việc vẫn nên được trả về qua giá trị trả về, handle của tác vụ hoặc kết quả `join()`. Tránh dùng ngữ cảnh như một đối tượng chứa kết quả để mọi nhánh cùng ghi.

## 3. Ngữ cảnh được ghi nhận lúc mở scope

### 3.1. Thứ tự thực thi đúng

Trình tự cần giữ là:

```text
Bind CONTEXT trên thread xử lý request
└── Mở StructuredTaskScope
    ├── Fork nhánh A: kế thừa ràng buộc đã ghi nhận
    ├── Fork nhánh B: kế thừa ràng buộc đã ghi nhận
    ├── Join để xử lý kết quả theo chính sách
    └── Đóng scope, đợi các luồng con kết thúc
Thoát tác vụ của ScopedValue: khôi phục ràng buộc trước đó
```

Điểm quan trọng nằm ở bước **mở scope**. Scope ghi nhận các ràng buộc scoped value đang có hiệu lực tại thời điểm đó. Các thread được scope tạo để chạy tác vụ con kế thừa những ràng buộc này.

Khi gọi `fork`, API kiểm tra ngữ cảnh ràng buộc của owner có khớp với lúc mở scope hay không. Vì vậy, không thể mở scope trước rồi tùy ý bind thêm ngữ cảnh ngay quanh từng lời gọi `fork` vào chính scope đó.

Quy tắc này giúp bảo đảm thread con không tiếp tục dùng một ràng buộc đã hết thời hạn ở thread cha. Xem phần [kế thừa ràng buộc scoped value của `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#Inheritance).

### 3.2. Truyền qua nhiều tầng

Nếu nhánh B mở scope riêng, nó trở thành owner của scope đó. Các nhánh B1, B2 kế thừa ràng buộc có hiệu lực khi B mở scope con:

```text
Request: req-42 / tenant-a / vi-VN
└── Scope ngoài
    ├── A: đọc hồ sơ
    │   └── đọc req-42 / tenant-a / vi-VN
    └── B: đọc danh mục
        └── Scope con
            ├── B1: đọc giá
            │   └── đọc req-42 / tenant-a / vi-VN
            └── B2: đọc tồn kho
                └── đọc req-42 / tenant-a / vi-VN
```

Không cần lặp lại thao tác bind tại mọi tầng nếu ngữ cảnh không thay đổi. Những phương thức được các nhánh gọi tiếp cũng có thể đọc dữ liệu nếu chúng truy cập được đúng khóa.

Đây là sự kế thừa **ràng buộc**, không phải sao chép sâu đối tượng `RequestContext`. Với các giá trị bất biến như record chứa chuỗi trong ví dụ, nhiều nhánh có thể cùng đọc an toàn.

## 4. Ví dụ hoàn chỉnh: truyền ngữ cảnh qua hai tầng scope

Lưu chương trình sau thành `ContextTreeDemo.java` nếu muốn chạy thử:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class ContextTreeDemo {
    private record RequestContext(
            String requestId,
            String tenantId,
            String language) {}

    private record Page(String profile, String catalog) {}

    private static final ScopedValue<RequestContext> CONTEXT =
            ScopedValue.newInstance();

    public static void main(String[] args) throws Exception {
        var request = new RequestContext("req-42", "tenant-a", "vi-VN");

        Page page = ScopedValue.where(CONTEXT, request)
                .call(ContextTreeDemo::loadPage);

        System.out.println(page.profile());
        System.out.println(page.catalog());
        System.out.println("context bound after request = " + CONTEXT.isBound());
    }

    private static Page loadPage()
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(ContextTreeDemo::loadProfile);
            var catalog = scope.fork(ContextTreeDemo::loadCatalog);

            scope.join();

            return new Page(profile.get(), catalog.get());
        }
    }

    private static String loadProfile() {
        return describe("profile");
    }

    private static String loadCatalog()
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open()) {
            var price = scope.fork(() -> describe("price"));
            var stock = scope.fork(() -> describe("stock"));

            scope.join();

            return price.get() + " | " + stock.get();
        }
    }

    private static String describe(String operation) {
        RequestContext context = currentContext();
        return operation + " -> "
                + context.requestId() + " / "
                + context.tenantId() + " / "
                + context.language();
    }

    private static RequestContext currentContext() {
        return CONTEXT.orElseThrow(() ->
                new IllegalStateException("request context is required"));
    }
}
```

Biên dịch và chạy bằng JDK 27:

```shell
javac --enable-preview --release 27 -encoding UTF-8 ContextTreeDemo.java
java --enable-preview ContextTreeDemo
```

Cờ preview cần thiết vì chương trình dùng `StructuredTaskScope`. Bản thân `ScopedValue` không còn yêu cầu preview trên JDK này. Cần bật preview cả khi biên dịch lẫn khi chạy; xem [hướng dẫn `javac`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) và [hướng dẫn `java`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

Kết quả dự kiến:

```text
profile -> req-42 / tenant-a / vi-VN
price -> req-42 / tenant-a / vi-VN | stock -> req-42 / tenant-a / vi-VN
context bound after request = false
```

Các nhánh có thể chạy và hoàn thành theo thứ tự khác nhau. Chương trình thu thập dữ liệu rồi in ở thread chính, nên kết quả trình bày không phụ thuộc vào thứ tự in log giữa các thread con.

Điểm cần đọc trong ví dụ:

1. `ScopedValue.where(...).call(...)` thiết lập ngữ cảnh trước khi `loadPage` mở scope ngoài.
2. `loadProfile` và `loadCatalog` nhận cùng ràng buộc dù không có tham số `RequestContext`.
3. Scope trong `loadCatalog` được mở trên thread con đang giữ ràng buộc kế thừa, nên `price` và `stock` cũng đọc đúng ngữ cảnh.
4. Mỗi scope được đóng trên đường trả kết quả về. Sau khi `call` ngoài cùng hoàn tất, ràng buộc request mới kết thúc.
5. Các chuỗi trong `Page` vẫn là dữ liệu kết quả bình thường; chúng không kéo dài ràng buộc `CONTEXT`.

`main` khai báo `throws Exception` để giữ ví dụ tập trung vào truyền ngữ cảnh. Trong mã ứng dụng, điểm nhận request cần xử lý các loại lỗi và yêu cầu ngắt theo hợp đồng của tầng đó.

## 5. Bind lại ngữ cảnh cho riêng một nhánh

Giả sử request dùng `vi-VN`, nhưng một nhánh cần dựng tài liệu bằng `en-US`. Nhánh này có thể mở một phạm vi ràng buộc mới. Những nhánh ngang hàng tiếp tục thấy ngữ cảnh của chúng.

Quy tắc sắp xếp vẫn giữ nguyên: **bind biến thể trước, rồi mở scope con bên trong biến thể đó**.

```text
Request: language = vi-VN
└── Scope ngoài
    ├── Nhánh thông thường: vi-VN
    └── Nhánh tài liệu: nhận vi-VN
        └── Bind lại language = en-US
            └── Mở scope con
                └── Nhánh render: en-US
        Thoát bind lại: nhánh tài liệu đọc lại vi-VN
Owner ngoài vẫn đọc vi-VN
```

### 5.1. Ví dụ độc lập

Chương trình `BranchContextDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class BranchContextDemo {
    private record RequestContext(
            String requestId,
            String tenantId,
            String language) {}

    private record BranchResults(
            String normal,
            String localized,
            String ownerLanguage) {}

    private static final ScopedValue<RequestContext> CONTEXT =
            ScopedValue.newInstance();

    public static void main(String[] args) throws Exception {
        var request = new RequestContext("req-42", "tenant-a", "vi-VN");

        BranchResults results = ScopedValue.where(CONTEXT, request)
                .call(BranchContextDemo::runBranches);

        System.out.println("normal = " + results.normal());
        System.out.println("localized = " + results.localized());
        System.out.println("owner = " + results.ownerLanguage());
        System.out.println("bound after request = " + CONTEXT.isBound());
    }

    private static BranchResults runBranches()
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open()) {
            var normal = scope.fork(() -> currentContext().language());
            var localized = scope.fork(BranchContextDemo::localizedBranch);

            scope.join();

            return new BranchResults(normal.get(), localized.get(),
                    currentContext().language());
        }
    }

    private static String localizedBranch() throws Exception {
        RequestContext inherited = currentContext();
        var english = new RequestContext(inherited.requestId(),
                inherited.tenantId(), "en-US");

        String childLanguage = ScopedValue.where(CONTEXT, english).call(() -> {
            try (var scope = StructuredTaskScope.open()) {
                var render = scope.fork(() -> currentContext().language());
                scope.join();
                return render.get();
            }
        });

        return "child=" + childLanguage
                + ", restored=" + currentContext().language();
    }

    private static RequestContext currentContext() {
        return CONTEXT.orElseThrow(() ->
                new IllegalStateException("request context is required"));
    }
}
```

Dùng JDK 27:

```shell
javac --enable-preview --release 27 -encoding UTF-8 BranchContextDemo.java
java --enable-preview BranchContextDemo
```

Kết quả dự kiến:

```text
normal = vi-VN
localized = child=en-US, restored=vi-VN
owner = vi-VN
bound after request = false
```

Không có thao tác sửa ngữ cảnh chung ở đây. Nhánh tài liệu tạo một `RequestContext` mới và bind lại **cùng khóa** trong phạm vi của riêng nó. Mã request và tenant được giữ từ ngữ cảnh kế thừa; ngôn ngữ được thay cho phần xử lý cần thiết.

Scope con được mở sau khi bind `english`, nên nhánh render kế thừa `en-US`. Sau khi scope con đóng và `call` kết thúc, nhánh tài liệu đọc lại ràng buộc kế thừa là `vi-VN`. Cơ chế bind lại và khôi phục được mô tả trong [phần rebinding của `ScopedValue`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html#Rebinding).

## 6. Giữ đúng ranh giới khi mở scope và bind ngữ cảnh

### 6.1. Mẫu sai: mở scope trước rồi bind ngay quanh `fork`

Đoạn sau minh họa một cấu trúc sai. Giả sử nó nằm trong lớp có khóa `CONTEXT`, biến `request` và phương thức đọc ngữ cảnh như các ví dụ trên:

```java
// Sai về cấu trúc: scope ghi nhận ràng buộc trước khi request được bind.
try (var scope = StructuredTaskScope.open()) {
    ScopedValue.where(CONTEXT, request).run(() -> {
        scope.fork(() -> currentContext().requestId());
    });

    scope.join();
}
```

Ràng buộc lúc `fork` khác ràng buộc lúc scope được mở. API phát hiện vi phạm này bằng `StructureViolationException`; nó không chọn ngữ cảnh mới theo ý của đoạn mã gọi `fork`.

Lỗi này vẫn thuộc cấu trúc phạm vi dù các trường dữ liệu có vẻ giống request trước đó. Không dùng việc so sánh giá trị bằng `equals` để suy ra rằng hai khoảng ràng buộc có thể thay thế tùy ý cho nhau.

Hợp đồng kiểm tra ràng buộc được nêu tại [API `fork(Callable)`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#fork(java.util.concurrent.Callable)).

### 6.2. Mẫu đúng: scope nằm hoàn toàn trong ràng buộc

Một phương thức bổ sung có thể viết theo cấu trúc:

```java
private static String executeForRequest(RequestContext request)
        throws Exception {
    return ScopedValue.where(CONTEXT, request).call(() -> {
        try (var scope = StructuredTaskScope.open()) {
            var child = scope.fork(() -> currentContext().requestId());
            scope.join();
            return child.get();
        }
    });
}
```

Scope mở, fork, join và đóng khi ràng buộc request vẫn có hiệu lực. Nếu cần đổi ngữ cảnh trong một nhánh, nhánh đó mở scope mới bên trong ràng buộc mới, như `localizedBranch` ở phần trước.

Không truyền scope của cha xuống cho thread con để thread con gọi `fork` vào đó. Các thao tác điều phối này thuộc owner của scope. Thread con có thể tự làm owner của một scope lồng nhau.

### 6.3. Không để scope thoát khỏi thời hạn ràng buộc

Tránh tạo scope trong một tác vụ của `ScopedValue` rồi trả scope ra ngoài để đóng về sau. Cách dùng đó làm ranh giới vòng đời không còn lồng đúng thứ tự. API có kiểm tra các vi phạm cấu trúc, bao gồm scope chưa được đóng khi thoát ràng buộc và việc đóng sai thứ tự.

`try`-with-resources đặt ngay bên trong tác vụ của `run` hoặc `call` giúp thể hiện quan hệ này trong mã nguồn. Xem [API `ScopedValue.Carrier`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.Carrier.html) và [quy định đóng `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#close()).

## 7. Điều gì xảy ra khi một nhánh thất bại hoặc bị hủy?

Truyền ngữ cảnh không có nghĩa mọi nhánh luôn thành công. Với scope mặc định trong các ví dụ JDK 27, một nhánh thất bại làm scope hủy các nhánh chưa hoàn tất và `join()` ném `ExecutionException`. Scope vẫn phải đóng, đợi các luồng con kết thúc.

Trong lúc nhánh con đang xử lý việc kết thúc, ràng buộc của nhánh vẫn còn hiệu lực. Chẳng hạn, một khối `finally` bên trong tác vụ con có thể đọc mã request để ghi nhận việc dọn dẹp. Tín hiệu interrupt không tự xóa ngữ cảnh giữa chừng.

Có thể theo dõi thứ tự theo vị trí mã:

| Vị trí thực thi | Ngữ cảnh được đọc |
| --- | --- |
| Thân tác vụ con | Ràng buộc tác vụ kế thừa, hoặc biến thể đang có hiệu lực của riêng nhánh |
| `finally` bên trong tác vụ con | Ràng buộc vẫn còn hiệu lực cho đến khi phần xử lý đó kết thúc |
| `catch` bao quanh scope nhưng vẫn nằm trong tác vụ của `ScopedValue.call` | Ngữ cảnh request ở phạm vi gọi đó |
| `catch` nằm ngoài lời gọi `ScopedValue.call` đã thoát | Ràng buộc có trước lời gọi; có thể là unbound |

Trong một nhánh bind lại ngôn ngữ, `finally` nằm trong tác vụ `en-US` vẫn đọc `en-US`. Chỉ sau khi tác vụ của lần bind lại kết thúc, nhánh mới trở về `vi-VN`.

### 7.1. `join()` và `close()` có trách nhiệm khác nhau

`join()` tạo điểm nhận kết quả theo chính sách. `close()` giữ bảo đảm vòng đời: không rời scope trong khi các luồng chạy tác vụ con vẫn chưa kết thúc.

Nếu tác vụ bỏ qua interrupt hoặc chặn trong một thao tác không ngắt được, việc đóng scope có thể bị kéo dài. Structured Concurrency không cưỡng chế mọi đoạn mã dừng ngay. Tác vụ cần dùng I/O có timeout hoặc khả năng hủy phù hợp, và kết thúc khi nhận yêu cầu ngắt.

Nhờ thứ tự lồng phạm vi, ngữ cảnh request không hết hiệu lực trong khi các nhánh có cấu trúc vẫn đang kết thúc. Bảo đảm này phụ thuộc vào việc bạn giữ đúng cấu trúc; nó không tự bao phủ công việc nền được tách ra qua một cơ chế khác.

### 7.2. Đọc kết quả theo chính sách đã chọn

Trong các ví dụ, scope mặc định join thành công nghĩa là các nhánh đều thành công, nên owner mới gọi `get()`. `Subtask.get()` không phải lời gọi chờ tương đương `Future.get()`.

Nếu dùng chính sách chỉ cần một kết quả thành công, không được suy ra mọi handle còn lại đều có dữ liệu. Hãy lấy kết quả theo hợp đồng của `Joiner` đang dùng. Hợp đồng đọc handle được mô tả trong [API `Subtask`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html).

## 8. Chia sẻ ràng buộc không làm đối tượng trở thành bất biến

`ScopedValue` không tự khóa hay sao chép sâu dữ liệu mà nó giữ. Nếu bind một `ArrayList` rồi để nhiều tác vụ thêm phần tử, bạn vẫn có việc ghi đồng thời vào cùng một đối tượng.

Record cũng không tự đóng băng các đối tượng nằm trong component của nó. Một record chứa collection có thể vẫn gián tiếp giữ dữ liệu thay đổi được.

Với nhãn ngữ cảnh dạng chuỗi, một biến thể có thể tạo bản sao không cho sửa như sau:

```java
import java.util.Map;

record TaggedContext(String requestId, Map<String, String> labels) {
    TaggedContext {
        labels = Map.copyOf(labels);
    }
}
```

Trong biến thể này, các khóa và giá trị của map là chuỗi, còn map được sao chép thành map không cho sửa. Nếu giá trị trong collection là một đối tượng mutable, vẫn cần xem tính bất biến của đối tượng đó; chỉ bọc collection là chưa đủ.

Nguyên tắc thiết kế dữ liệu cho cây tác vụ:

- Dùng ngữ cảnh nhỏ, chủ yếu chứa thông tin nhận diện và cấu hình chỉ đọc.
- Tạo đối tượng ngữ cảnh mới khi một nhánh cần biến thể; giữ các thuộc tính cần kế thừa.
- Trả kết quả của nhánh qua kết quả tác vụ, rồi tổng hợp sau khi chờ đúng điều kiện.
- Nếu buộc phải chia sẻ dữ liệu mutable, thiết kế đồng bộ hóa của chính dữ liệu đó một cách rõ ràng.

Việc thoát phạm vi chỉ khôi phục ràng buộc mà lần đọc khóa nhìn thấy. Nó không hoàn tác thao tác ghi file, cập nhật dữ liệu hoặc sửa đối tượng đã xảy ra.

Cũng cần phân biệt unbound với giải phóng bộ nhớ ngay lập tức. Nếu mã ứng dụng giữ tham chiếu tới đối tượng ngữ cảnh hoặc một carrier, đối tượng đó có thể vẫn còn sống sau khi lần ràng buộc kết thúc. Vì vậy, nên giữ ngữ cảnh vừa đủ cho công việc của cây tác vụ.

## 9. Những ranh giới không tự truyền ngữ cảnh

### 9.1. Một lambda được tạo trong request không tự giữ ràng buộc

Lambda chứa lời gọi `currentContext()` sẽ đọc ngữ cảnh khi nó chạy. Việc tạo lambda trong phạm vi request không tự chụp ràng buộc của request để dùng mãi về sau.

Nếu trả lambda ra ngoài rồi chạy sau khi request đã kết thúc, nó có thể không còn ngữ cảnh. Nếu chạy lambda ấy trong ngữ cảnh request khác, việc đọc khóa sẽ theo ràng buộc tại thời điểm thực thi.

Khi thật sự cần một dữ liệu cho công việc về sau, hãy lấy đúng dữ liệu đó làm đầu vào của công việc và xác định vòng đời mới. Không dựa vào vị trí khai báo lambda để suy ra ngữ cảnh sẽ được truyền.

### 9.2. Tự tạo thread hoặc gửi executor không có cùng bảo đảm

Cơ chế trong bài được xác định cho các tác vụ do `StructuredTaskScope` fork. Không suy ra rằng `new Thread`, `Thread.startVirtualThread`, một executor hoặc `CompletableFuture` mặc nhiên kế thừa cùng ràng buộc.

Nếu một thư viện tự tạo công việc qua cơ chế khác, cần kiểm tra hợp đồng truyền ngữ cảnh của thư viện. Bản thân việc thread đó là virtual thread không biến nó thành nhánh có cấu trúc của scope request.

Một job cần tiếp tục sau khi request đã trả về có vòng đời khác với cây tác vụ trong bài. Hãy xác định dữ liệu đầu vào của job và ngữ cảnh của job một cách tường minh, thay vì dựa vào ràng buộc request còn tồn tại.

### 9.3. Qua HTTP hoặc hàng đợi là một lần truyền dữ liệu khác

`ScopedValue` là cơ chế trong tiến trình Java. Nó không tự biến mã request thành HTTP header, metadata của message hay một span ở tiến trình khác.

Nếu tác vụ gọi một dịch vụ ngoài, lớp tích hợp cần đọc dữ liệu cần gửi và ánh xạ theo giao thức đang dùng. Ở bên nhận, mã tiếp nhận lại xây dựng ngữ cảnh cục bộ từ dữ liệu hợp lệ. Tương tự, logger không tự có trường request chỉ vì một khóa `ScopedValue` đã được bind; điểm tích hợp ghi log phải đọc ngữ cảnh hoặc dùng hỗ trợ của framework.

Phân biệt này giúp bạn kiểm tra đúng nơi khi ngữ cảnh có trong một phương thức Java nhưng không xuất hiện ở dịch vụ hoặc bản ghi log phía ngoài.

## 10. Đọc lỗi và tổ chức mã ứng dụng

### 10.1. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể có | Cách tổ chức lại |
| --- | --- | --- |
| `CONTEXT.get()` ném `NoSuchElementException` | Không có ràng buộc trên thread đang đọc | Bind trước khi mở scope và kiểm tra cơ chế tạo tác vụ |
| `currentContext()` của ví dụ ném `IllegalStateException` | Điểm đọc bắt buộc được gọi ngoài ngữ cảnh | Kiểm tra ranh giới request và nơi thực thi callback |
| `fork` ném `StructureViolationException` | Ràng buộc hiện tại khác thời điểm mở scope | Mở scope sau khi bind đúng ngữ cảnh; dùng scope mới cho biến thể của nhánh |
| `WrongThreadException` | Thread con gọi thao tác điều phối trên scope của cha | Để owner điều phối; thread con mở scope riêng nếu cần |
| Nhánh ngang hàng thấy dữ liệu bị sửa | Nhiều nhánh cùng tham chiếu một đối tượng mutable | Dùng dữ liệu bất biến và bind biến thể bằng đối tượng mới |
| Log sau request không còn mã request qua khóa | Lời gọi nằm ngoài thời hạn ràng buộc | Ghi nhận ở vị trí đúng phạm vi hoặc truyền dữ liệu cần dùng một cách tường minh |
| Timeout hoặc hủy nhưng request chưa kết thúc | Scope đang đợi nhánh chưa chịu thoát | Kiểm tra interrupt, timeout I/O và việc đóng các scope lồng nhau |
| Compile không khớp `open`, `join` hoặc kiểu ngoại lệ | Trộn API từ các lần preview khác nhau | Dùng tài liệu và toolchain của cùng JDK |

### 10.2. Cách chia trách nhiệm

Tại điểm nhận request, hãy tạo ngữ cảnh một lần sau khi xác định dữ liệu đầu vào, rồi bind nó quanh toàn bộ phần xử lý cần dùng. Lớp điều phối mở scope trong phạm vi đó, chọn chính sách kết quả và chờ các nhánh liên quan. Các lớp dịch vụ phía dưới chỉ đọc những dữ liệu ngữ cảnh thực sự cần.

Một nhánh cần tùy chọn riêng tạo ngữ cảnh mới từ ngữ cảnh kế thừa, bind biến thể và mở scope con bên trong. Sau khi nhánh hoàn tất, phần xử lý của nhánh trở lại ngữ cảnh kế thừa; owner và các nhánh ngang hàng giữ ngữ cảnh của chúng.

Các tham số nghiệp vụ như mã sản phẩm, số lượng hoặc nội dung biểu mẫu vẫn nên được truyền theo chữ ký phương thức khi đó là đầu vào trực tiếp của thao tác. Ngữ cảnh ngầm phù hợp với dữ liệu đi xuyên nhiều lớp nhưng không cần xuất hiện ở mọi chữ ký. Điểm đọc nên được đóng gói rõ để người bảo trì thấy phương thức đang phụ thuộc vào ngữ cảnh request.

Khi nhìn một cây tác vụ, hãy xác định đồng thời **scope nào sở hữu nhánh** và **ràng buộc nào có hiệu lực lúc scope đó mở**. Hai thông tin này cho biết nhánh đọc ngữ cảnh nào, biến thể được truyền tới đâu và khi nào toàn bộ quá trình có thể kết thúc an toàn trong ranh giới request.
