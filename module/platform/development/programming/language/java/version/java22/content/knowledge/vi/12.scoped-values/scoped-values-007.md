# Truyền ngữ cảnh theo cơ chế kế thừa được hỗ trợ bởi StructuredTaskScope của JDK sử dụng

## Phạm vi và phiên bản sử dụng

Bài học thuộc chương **Scoped Value** của module **JAVA_VERSION_JAVA22**, dành cho việc học các tính năng có mặt ở Java 22 và còn hữu ích trong Java hiện đại. Trọng tâm là truyền ngữ cảnh từ tác vụ cha xuống các tác vụ con bằng `ScopedValue`, với vòng đời do `StructuredTaskScope` quản lý.

Ở Java 22, cả hai API đều ở trạng thái preview; đây không phải phiên bản đầu tiên xuất hiện của chúng. Cơ chế kế thừa ngữ cảnh vẫn còn giá trị, nhưng chữ ký API đã thay đổi qua các phiên bản. Có thể đối chiếu trạng thái ban đầu tại tài liệu [ScopedValue của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/ScopedValue.html) và [StructuredTaskScope của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

**Mốc đối chiếu của bài là ngày 25/11/2026, với ví dụ dùng JDK 27:**

| Thành phần | Trạng thái và cách sử dụng trong bài |
| --- | --- |
| `ScopedValue` | API chính thức từ Java 25; riêng API này không còn yêu cầu bật preview. |
| `StructuredTaskScope` | Vẫn là API preview trong Java 27; ví dụ kết hợp hai API cần bật preview. |
| Cú pháp mở task scope | Dùng `StructuredTaskScope.open()` theo API Java 27. |
| Khả năng chạy trên JDK 22 | Ví dụ không nhắm biên dịch nguyên trạng trên JDK 22. Học cơ chế từ Java 22 bằng hình thức API hiện hành. |

Thông tin này được xác nhận trong [ScopedValue của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html) và [các thay đổi của JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html). Bài không dùng các biến thể API preview cũ làm mẫu triển khai mới.

## 1. Bài toán: nhiều tác vụ con cần cùng một ngữ cảnh yêu cầu

Giả sử một endpoint tổng hợp màn hình người dùng cần thực hiện đồng thời hai công việc:

- Đọc hồ sơ người dùng trong tenant hiện tại.
- Đếm thông báo chưa đọc của cùng người dùng.

Cả hai cần `requestId`, `tenantId` và `userId`. Các phương thức trung gian chỉ điều phối công việc có thể không cần xử lý trực tiếp những giá trị này.

Truyền một đối tượng ngữ cảnh qua tham số vẫn là lựa chọn rõ ràng khi quan hệ gọi đơn giản. `ScopedValue` phù hợp khi ngữ cảnh phục vụ xuyên suốt một chuỗi lời gọi và cần đến được những lớp xử lý sâu hơn. Thiết kế ở đây gồm ba phần:

1. Biên xử lý yêu cầu tạo một bản ngữ cảnh đã được xác thực.
2. Biên đó bind ngữ cảnh vào một khóa `ScopedValue` cho thời gian xử lý.
3. Các tác vụ con được fork trong `StructuredTaskScope` kế thừa binding để đọc ngữ cảnh.

Trong bài, **binding** là liên kết giữa một khóa `ScopedValue` và giá trị đang có hiệu lực. **Kế thừa** nghĩa là tác vụ con có thể đọc giá trị qua chính khóa đó; không có nghĩa là Java sao chép sâu đối tượng ngữ cảnh cho từng tác vụ.

Luồng dữ liệu có chủ đích đi từ nơi thiết lập ngữ cảnh xuống nơi sử dụng. Kết quả nghiệp vụ đi ngược về cha qua kết quả của các `Subtask`, giúp phân biệt dữ liệu đầu vào dùng chung với kết quả của từng công việc.

## 2. Hai phạm vi cần lồng đúng thứ tự

Có hai loại scope trong cùng một đoạn chương trình:

| Loại scope | Điều nó giới hạn |
| --- | --- |
| Scope binding của `ScopedValue` | Khoảng thực thi mà liên kết ngữ cảnh có hiệu lực. |
| Task scope của `StructuredTaskScope` | Vòng đời của nhóm tác vụ con được fork trong scope. |

Task scope phải nằm bên trong khoảng thực thi có binding mà các tác vụ cần kế thừa:

```text
Bắt đầu binding CONTEXT = ngữ cảnh yêu cầu
│
├─ Mở StructuredTaskScope: ghi nhận các bindings hiện hành
│  ├─ Fork tác vụ A: kế thừa bindings đã ghi nhận
│  ├─ Fork tác vụ B: kế thừa bindings đã ghi nhận
│  ├─ Join: nhận kết quả hoặc lỗi theo chính sách của scope
│  └─ Close: chờ các luồng tác vụ con kết thúc
│
└─ Kết thúc binding: trở lại binding trước đó hoặc trạng thái chưa bound
```

Điểm quan trọng là **bindings được chụp khi mở task scope**. Khi `fork`, JDK kiểm tra bindings hiện hành có khớp với lúc mở hay không. Quy tắc này được mô tả trong phần [kế thừa scoped value bindings của StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#scoped-value-inheritance).

Với cách lồng trên, không còn luồng con của task scope tiếp tục dùng binding sau khi scope ngoài đã kết thúc. Trên đường có lỗi, `close()` vẫn chờ các luồng con kết thúc; đây là phần bảo đảm vòng đời mà riêng việc gọi `join()` chưa thể thay thế.

## 3. Ví dụ đầy đủ: hai tác vụ con đọc chung ngữ cảnh

Lưu đoạn sau thành `ScopedContextDemo.java` trong môi trường học có JDK 27. Các hàm đọc dữ liệu dùng giá trị mô phỏng để tập trung vào việc truyền ngữ cảnh.

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class ScopedContextDemo {
    private static final ScopedValue<RequestContext> CONTEXT =
            ScopedValue.newInstance();

    record RequestContext(
            String requestId,
            String tenantId,
            String userId) {
    }

    record Dashboard(
            String requestId,
            String profile,
            int unreadCount) {
    }

    static Dashboard handle(RequestContext context) throws Exception {
        return ScopedValue.where(CONTEXT, context)
                .call(ScopedContextDemo::loadDashboard);
    }

    static Dashboard loadDashboard()
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(ScopedContextDemo::loadProfile);
            var unread = scope.fork(ScopedContextDemo::loadUnreadCount);

            scope.join();

            return new Dashboard(
                    CONTEXT.get().requestId(),
                    profile.get(),
                    unread.get());
        }
    }

    static String loadProfile() {
        RequestContext context = CONTEXT.get();
        return context.tenantId() + "/" + context.userId();
    }

    static int loadUnreadCount() {
        RequestContext context = CONTEXT.get();
        return context.userId().equals("user-42") ? 3 : 0;
    }

    public static void main(String[] args) throws Exception {
        RequestContext context = new RequestContext(
                "req-007", "tenant-acme", "user-42");

        Dashboard dashboard = handle(context);
        System.out.println(dashboard);
        System.out.println("Context còn bound: " + CONTEXT.isBound());
    }
}
```

Biên dịch và chạy bằng công cụ của **cùng JDK 27**:

```shell
javac --enable-preview --release 27 ScopedContextDemo.java
java --enable-preview ScopedContextDemo
```

Kết quả dự kiến:

```text
Dashboard[requestId=req-007, profile=tenant-acme/user-42, unreadCount=3]
Context còn bound: false
```

Các cờ preview cần thiết vì ví dụ dùng `StructuredTaskScope`. Khi chuyển sang một bản JDK khác, cần kiểm tra API và biên dịch lại bằng bản đó; không chỉ sửa con số ở `--release`. Hướng dẫn nền tảng được trình bày trong [Structured Concurrency của Java 27](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html).

### Ngữ cảnh đi qua ví dụ như thế nào?

`CONTEXT` là khóa dùng chung có quyền truy cập giới hạn trong lớp. Giá trị theo từng yêu cầu được bind khi `handle` gọi `call`; trường `static final` không biến ngữ cảnh yêu cầu thành một biến toàn cục chứa giá trị duy nhất.

`loadDashboard` chạy trong scope binding đó và mở task scope. Hai phương thức `loadProfile` và `loadUnreadCount` chạy trong các luồng do task scope tạo ra. Chúng gọi `CONTEXT.get()` mà không cần nhận thêm tham số ngữ cảnh.

Với cấu hình mặc định, mỗi tác vụ được fork chạy trên một virtual thread. Chính task scope cung cấp cơ chế kế thừa; việc các luồng mặc định là virtual thread không phải điều kiện đủ để một luồng bất kỳ nhận được binding.

Sau `join()` thành công, chương trình lấy hai kết quả và tạo `Dashboard`. `Subtask.get()` ở đây là đọc kết quả của tác vụ đã hoàn tất thành công, không thay thế thao tác chờ của `join()`. Điều kiện truy xuất kết quả được quy định tại [StructuredTaskScope.Subtask của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html).

Khi `handle` hoàn tất, binding đã thiết lập được gỡ khỏi phạm vi thực thi hiện tại. Trong ví dụ không có binding ngoài, nên `isBound()` trả về `false`. Nếu có binding ngoài cho cùng khóa, giá trị ngoài được khôi phục. Cơ chế khôi phục cũng áp dụng khi callback kết thúc bằng exception, theo [ScopedValue.Carrier.call](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.Carrier.html#call(java.lang.ScopedValue.CallableOp)).

## 4. Vì sao bind trước khi fork vẫn có thể sai?

Một cách hiểu dễ nhầm là: “Chỉ cần bind trước lệnh `fork` thì tác vụ con sẽ nhận ngữ cảnh mới”. Điều này bỏ qua thời điểm mở task scope.

Đoạn dưới minh họa **cách lồng sai**. Các tên `CONTEXT` và `RequestContext` dùng lại từ ví dụ đầy đủ; đoạn mã được đặt trong một phương thức khai báo `throws Exception`:

```java
RequestContext context = new RequestContext(
        "req-wrong", "tenant-acme", "user-42");

try (var scope = StructuredTaskScope.open()) {
    // Task scope đã chụp bindings trước khi có binding mới này.
    ScopedValue.where(CONTEXT, context).run(() -> {
        scope.fork(() -> CONTEXT.get().tenantId());
    });

    scope.join();
}
```

Tại `fork`, bindings không khớp với thời điểm mở scope, dẫn đến `StructureViolationException`. Lỗi này cũng có thể xuất hiện khi scope được mở dưới một binding cũ, rồi mã cha rebind cùng khóa trước khi fork. Đây là vi phạm cấu trúc scope, không phải một cách truyền ngữ cảnh khác cho riêng tác vụ mới.

Sửa bằng cách đưa **cả việc mở, fork, join và đóng task scope** vào bên trong binding cần sử dụng:

```java
String tenant = ScopedValue.where(CONTEXT, context).call(() -> {
    try (var scope = StructuredTaskScope.open()) {
        var subtask = scope.fork(() -> CONTEXT.get().tenantId());
        scope.join();
        return subtask.get();
    }
});
```

Quy tắc cần nhớ là **bind → mở scope → fork → join → đóng scope → kết thúc binding**. Nếu một nhánh cần ngữ cảnh khác, hãy thiết lập một phạm vi lồng đúng rồi mở task scope riêng cho nhánh đó.

## 5. Kế thừa nhiều tầng và rebinding trong tác vụ con

Tác vụ con có thể mở một task scope mới để chia nhỏ công việc. Nếu nó đang dùng ngữ cảnh kế thừa từ cha, các tác vụ ở tầng tiếp theo cũng nhận được ngữ cảnh đó.

Rebinding cho phép một nhánh có giá trị khác trong một khoảng thực thi lồng. Việc này không thay binding của cha hoặc của nhánh anh em. Sau khi khoảng lồng kết thúc, tác vụ con lại nhìn thấy binding đã kế thừa trước đó.

Ví dụ sau tiếp tục dùng các kiểu của `ScopedContextDemo`. Giả sử đoạn mã nằm trong một phương thức `throws Exception`, được gọi **bên trong binding của một yêu cầu**:

```java
try (var outer = StructuredTaskScope.open()) {
    var branch = outer.fork(() -> {
        RequestContext inherited = CONTEXT.get();
        RequestContext branchContext = new RequestContext(
                inherited.requestId() + "/branch",
                inherited.tenantId(),
                inherited.userId());

        return ScopedValue.where(CONTEXT, branchContext).call(() -> {
            // Scope mới được mở sau rebinding của nhánh.
            try (var inner = StructuredTaskScope.open()) {
                var leaf = inner.fork(() -> CONTEXT.get().requestId());
                inner.join();
                return leaf.get();
            }
        });
    });

    var sibling = outer.fork(() -> CONTEXT.get().requestId());

    outer.join();
    System.out.println(branch.get());
    System.out.println(sibling.get());
    System.out.println(CONTEXT.get().requestId());
}
```

Với ngữ cảnh ngoài có `requestId = "req-007"`, ba dòng in lần lượt là:

```text
req-007/branch
req-007
req-007
```

`leaf` kế thừa ngữ cảnh nhánh vì `inner` mở trong rebinding đó. `sibling` thuộc task scope ngoài nên tiếp tục dùng ngữ cảnh gốc. Hậu tố `/branch` chỉ giúp quan sát ví dụ; dịch vụ thực tế có thể giữ nguyên request ID và dùng trường riêng để nhận diện nhánh.

Điểm phân biệt với lỗi ở mục trước: tác vụ con không dùng lại `outer` để fork dưới binding mới. Nó mở `inner` sau khi rebind. Tác vụ con cũng không sở hữu `outer`, nên không được thay cha gọi các thao tác `fork`, `join` hay `close` trên scope đó.

## 6. Ranh giới kế thừa: không tự lan sang mọi công việc bất đồng bộ

Một lambda được tạo ra trong scope binding không tự đóng gói binding để mang tới bất kỳ nơi thực thi nào. Cần phân biệt việc lambda giữ tham chiếu đến biến Java với việc luồng thực thi có binding của `ScopedValue`.

| Cách thực thi | Cách hiểu về ngữ cảnh |
| --- | --- |
| Gọi phương thức trực tiếp trong callback `call` hoặc `run` | Chạy trên luồng hiện tại, trong binding đang có hiệu lực. |
| `scope.fork(...)` với bindings hợp lệ | Tác vụ nhận bindings mà task scope đã chụp. |
| Tác vụ con mở một task scope mới | Scope mới chụp bindings hiện hành của tác vụ con. |
| `Thread.startVirtualThread(...)` hoặc tạo thread trực tiếp | Không tự kế thừa scoped value bindings chỉ vì được tạo trong callback. |
| Gửi việc vào executor hoặc `CompletableFuture` | Không có bảo đảm truyền binding của `StructuredTaskScope`; phải xem cơ chế thực thi cụ thể. |
| Gửi thông điệp sang dịch vụ khác | Cần truyền metadata qua giao thức rồi thiết lập ngữ cảnh ở nơi nhận. |

Với executor hoặc một stage của `CompletableFuture`, mã đôi khi chạy ngay trên luồng hiện tại và vì thế đọc được binding đang có. Không nên lấy trường hợp đó làm cam kết truyền ngữ cảnh sang một luồng khác.

Đoạn sau cho thấy việc tạo virtual thread trực tiếp không cung cấp kế thừa. Đặt trong một phương thức `throws Exception` của lớp ví dụ:

```java
RequestContext context = new RequestContext(
        "req-direct", "tenant-acme", "user-42");

ScopedValue.where(CONTEXT, context).call(() -> {
    Thread worker = Thread.startVirtualThread(() -> {
        System.out.println(CONTEXT.isBound()); // false
    });
    worker.join();
    return null;
});
```

Chủ động `join` luồng này giúp quản lý vòng đời trong đoạn mã, nhưng không biến nó thành tác vụ được fork bởi `StructuredTaskScope`. Giới hạn chia sẻ giữa các luồng được nêu ở phần [Inheritance của ScopedValue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html#inheritance).

Nếu công việc cần tiếp tục sau khi yêu cầu đã kết thúc, hãy thiết kế dữ liệu đầu vào riêng cho công việc đó. Ví dụ, một job gửi email có thể nhận `tenantId`, mã thông báo và thông tin định tuyến cần thiết trong payload. Giữ cả ngữ cảnh của yêu cầu để dùng về sau làm mờ ranh giới vòng đời và dễ giữ lại dữ liệu thừa.

## 7. Binding ổn định không làm đối tượng tự trở thành bất biến

Trong ví dụ đầy đủ, `RequestContext` chỉ chứa `String`, nên có thể chia sẻ mà không có các trường dữ liệu bị sửa đồng thời. Tất cả tác vụ kế thừa có thể cùng nhìn tới một đối tượng ngữ cảnh.

Nếu đổi thành `record RequestContext(List<String> roles)`, khai báo `record` chỉ làm trường tham chiếu không bị gán lại sau khi tạo; một `ArrayList` được truyền vào vẫn có thể bị sửa. Binding không thay thế khóa, collection an toàn luồng hoặc thiết kế đối tượng bất biến.

Một cách xây dựng bản chụp quyền đọc là:

```java
import java.util.List;

record AuthorizationSnapshot(List<String> permissions) {
    AuthorizationSnapshot {
        permissions = List.copyOf(permissions);
    }
}
```

Với các phần tử `String`, bản sao danh sách không cho phép thay đổi này phù hợp để chia sẻ. Nếu phần tử là đối tượng có trạng thái thay đổi được, vẫn phải xử lý tính bất biến hoặc đồng bộ hóa của từng phần tử.

Yêu cầu giá trị dùng chung phải bất biến hoặc được đồng bộ hóa thích hợp được ghi trong [ScopedValue của Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ScopedValue.html). Khi thiết kế ngữ cảnh, ưu tiên metadata nhỏ và ổn định: định danh yêu cầu, tenant, người dùng, locale hoặc bản chụp quyền cần thiết.

Không dùng ngữ cảnh làm nơi gom kết quả có thể bị nhiều nhánh sửa cùng lúc. Với ví dụ dashboard, hồ sơ và số thông báo nên được trả về từ từng tác vụ rồi tổng hợp ở cha. Cũng không nên chia sẻ một kết nối cơ sở dữ liệu hay session chỉ vì có thể đặt nó vào `ScopedValue`; tính an toàn luồng và vòng đời của tài nguyên vẫn cần được đánh giá riêng.

## 8. Lỗi, hủy tác vụ và kết thúc binding

Trong ví dụ dùng `StructuredTaskScope.open()` mặc định của JDK 27:

- Nếu mọi tác vụ thành công, `join()` hoàn tất bình thường; cha có thể đọc kết quả thành công.
- Nếu một tác vụ thất bại, scope hủy công việc còn lại và `join()` ném `ExecutionException`, với lỗi tác vụ làm nguyên nhân.
- Nếu luồng cha bị ngắt khi chờ `join()`, phương thức có thể ném `InterruptedException`.
- Khi rời `try-with-resources`, `close()` vẫn bảo đảm chờ các luồng tác vụ con kết thúc.

Chính sách tổng hợp kết quả có thể thay đổi khi chọn một `Joiner` khác. Vì vậy, không áp dụng giả định “mọi tác vụ đều thành công khi join trả về” cho mọi cấu hình; cần đọc hợp đồng của joiner. Các chính sách được mô tả tại [StructuredTaskScope.Joiner của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html).

Hủy tác vụ dựa vào khả năng hợp tác với interruption. Một tác vụ bỏ qua ngắt hoặc mắc kẹt trong thao tác không ngắt được có thể khiến `close()` chờ rất lâu. Binding ngoài vẫn bao quanh giai đoạn đóng scope; cơ chế này không cung cấp cam kết rằng yêu cầu luôn kết thúc ngay khi một nhánh lỗi. Chi tiết chờ khi đóng scope được nêu trong [StructuredTaskScope của Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#close()).

Ở tầng xử lý thực tế, hãy lan truyền `InterruptedException` khi có thể. Nếu bắt nó tại ranh giới không cho phép ném tiếp, cần có chính sách giữ tín hiệu ngắt, thường bằng `Thread.currentThread().interrupt()`, và kết thúc công việc thích hợp.

Kết thúc binding là khôi phục cách tra cứu ngữ cảnh trên luồng hiện tại. Nó không tự đóng tài nguyên chứa trong giá trị, không xóa mọi tham chiếu tới đối tượng và không thu hồi dữ liệu đã được mã khác sao chép. Vì thế, cần giữ `ScopedValue` đúng vai trò truyền ngữ cảnh có phạm vi.

## 9. Áp dụng vào một dịch vụ xử lý yêu cầu

Với endpoint tổng hợp dữ liệu theo tenant, một thiết kế dễ theo dõi là:

1. Tầng biên xác thực người dùng, xác định tenant được phép truy cập và tạo đối tượng ngữ cảnh bất biến.
2. Tầng biên bind đối tượng rồi gọi phần xử lý yêu cầu.
3. Phần điều phối mở task scope và fork những công việc cần hoàn tất trong yêu cầu đó.
4. Mỗi tác vụ đọc ngữ cảnh qua một API nội bộ có tên rõ nghĩa, chẳng hạn `currentRequestContext()`.
5. Cha join, tổng hợp kết quả và đóng task scope trước khi rời binding.

Việc một repository đọc được `tenantId` không tự tạo ra điều kiện lọc tenant cho truy vấn. Repository vẫn phải dùng giá trị đó trong logic truy cập dữ liệu. Tương tự, logger không tự bổ sung `requestId` nếu thư viện logging chưa có phần tích hợp đọc ngữ cảnh.

Nếu một tác vụ gọi HTTP sang dịch vụ khác, client phải chủ động chuyển metadata được phép vào header hoặc payload. Dịch vụ nhận xác minh dữ liệu đầu vào rồi tạo binding của riêng nó. `ScopedValue` không truyền đối tượng Java qua mạng và cũng không thay thế việc kiểm tra quyền.

Các dấu hiệu cần xem lại thiết kế:

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| `CONTEXT.get()` báo chưa có giá trị | Lời gọi đã ra ngoài binding hoặc chạy trên luồng không được kế thừa; với ngữ cảnh bắt buộc, đừng che lỗi bằng một tenant mặc định. |
| `StructureViolationException` tại `fork` | Task scope có được mở trước khi bind hoặc rebind hay không. |
| Hai nhánh cùng làm thay đổi dữ liệu ngữ cảnh | Giá trị có chứa collection hoặc đối tượng thay đổi được hay không. |
| Một nhánh cần ngữ cảnh riêng | Rebind trong nhánh và mở task scope con nếu cần fork thêm. |
| Yêu cầu chờ lâu sau khi hủy | Tác vụ và lời gọi I/O có phản hồi interruption hay không. |
| Job nền cần chạy sau khi trả response | Job cần payload và vòng đời riêng thay cho phụ thuộc vào binding của yêu cầu. |

Khi bảo trì mã, hãy thể hiện rõ nơi thiết lập ngữ cảnh và nơi mở task scope. Thứ tự lồng này giúp người đọc kiểm tra được cả dữ liệu mà tác vụ con nhận lẫn thời điểm những tác vụ đó chắc chắn đã kết thúc.
