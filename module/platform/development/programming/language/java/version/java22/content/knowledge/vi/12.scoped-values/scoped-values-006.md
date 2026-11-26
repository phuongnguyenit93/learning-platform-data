# Phạm vi lồng nhau, che khuất ràng buộc và khôi phục ngữ cảnh khi thoát phạm vi

## 1. Bối cảnh và mục tiêu

Trong một request, phần lớn xử lý có thể dùng ngôn ngữ `vi-VN`, nhưng một bước xuất tài liệu cần dùng `en-US`. Bước đó có thể gọi tiếp nhiều phương thức khác. Ta muốn mọi phương thức trong bước xuất tài liệu thấy `en-US`, rồi phần xử lý request tiếp tục thấy `vi-VN` ngay khi bước này kết thúc, kể cả khi có ngoại lệ.

`ScopedValue` giải quyết tình huống này bằng **ràng buộc có thời hạn theo luồng thực thi**. Bài học tập trung vào ba thao tác: mở phạm vi con, đọc ràng buộc gần nhất của cùng khóa và trở lại ngữ cảnh trước đó khi phạm vi con kết thúc.

Về phiên bản: Java 22 cung cấp Scoped Values ở lần preview thứ hai, JEP 464; đây không phải tính năng xuất hiện lần đầu trong Java 22. Từ Java 25, Scoped Values đã trở thành API chính thức theo JEP 506. Nội dung dưới đây giữ các nguyên lý còn áp dụng và dùng cú pháp `ScopedValue.where(...).run(...)` hoặc `.call(...)`. Các chương trình hoàn chỉnh lấy **JDK 25** làm mốc chạy, không cần bật preview chỉ để dùng `ScopedValue`. Xem [ghi chú phát hành JDK 22](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) và [ghi chú phát hành JDK 25](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html).

Sau bài học, bạn cần giải thích được giá trị mà `get()` đọc tại từng điểm trong chuỗi gọi, vị trí khôi phục khi có `return` hoặc ngoại lệ, và giới hạn của việc khôi phục ngữ cảnh.

## 2. Khóa, ràng buộc và phạm vi động

Giả sử có một khóa:

```java
private static final ScopedValue<String> LANGUAGE = ScopedValue.newInstance();
```

Cần tách ba khái niệm:

| Khái niệm | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Khóa | Đối tượng `LANGUAGE` | Xác định dữ liệu ngữ cảnh cần đọc |
| Ràng buộc | `LANGUAGE` gắn với `"vi-VN"` | Giá trị có hiệu lực trong một lần thực thi có phạm vi |
| Phạm vi động | Quá trình thực thi tác vụ được truyền cho `run` hoặc `call`, cùng các lời gọi đồng bộ bên trong | Quyết định nơi ràng buộc có thể được đọc trên luồng hiện tại |

`static final` giữ cố định tham chiếu tới khóa. Nó không biến ngôn ngữ thành một giá trị chung cho mọi request.

### 2.1. Quy tắc đọc tại một thời điểm

Với một khóa cụ thể, có thể suy luận theo trình tự:

1. Xét các ràng buộc đang có hiệu lực trên luồng hiện tại.
2. Chọn ràng buộc gần nhất của **chính đối tượng khóa đó**.
3. Nếu không có ràng buộc, khóa đang ở trạng thái *unbound*; gọi `get()` sẽ ném `NoSuchElementException`.

Đây là mô hình suy luận theo các lớp phạm vi, không phải yêu cầu bạn tự xây dựng một ngăn xếp hay dựa vào chi tiết triển khai JVM.

### 2.2. Phạm vi động không đồng nhất với dấu ngoặc nhọn

Một khối `{ ... }` hoặc một lời gọi phương thức thông thường không tự tạo ràng buộc mới. Ràng buộc tồn tại trong lúc tác vụ của `run` hoặc `call` thực thi. Những phương thức được tác vụ gọi trực tiếp hoặc gián tiếp có thể đọc ngữ cảnh nếu chúng truy cập được khóa.

Một phương thức được khai báo ở cuối lớp vẫn thấy ràng buộc của phạm vi đang gọi nó. Nơi khai báo phương thức không quyết định giá trị mà nó đọc. Các quy tắc này được mô tả trong [API `ScopedValue` của Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html).

## 3. Ba cấp lồng nhau và việc che khuất ràng buộc

**Rebinding**, hay ràng buộc lại, mở một phạm vi con dùng giá trị khác cho cùng khóa. Trong phạm vi con, ràng buộc mới **che khuất** ràng buộc ngoài. Khi phạm vi con kết thúc, ràng buộc ngoài lại được nhìn thấy.

Lưu chương trình sau thành `NestedScopesDemo.java` nếu muốn chạy thử:

```java
public class NestedScopesDemo {
    private static final ScopedValue<String> LANGUAGE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        show("0. before");

        ScopedValue.where(LANGUAGE, "vi-VN").run(() -> {
            show("1. request");
            exportDocument();
            show("6. request again");

            ScopedValue.where(LANGUAGE, "fr-FR")
                    .run(() -> show("7. sibling"));

            show("8. after sibling");
        });

        show("9. after");
    }

    private static void exportDocument() {
        ScopedValue.where(LANGUAGE, "en-US").run(() -> {
            show("2. export");

            ScopedValue.where(LANGUAGE, "ja-JP").run(() -> {
                show("3. appendix");
                renderFooter();
            });

            show("5. export again");
        });
    }

    private static void renderFooter() {
        show("4. footer");
    }

    private static void show(String step) {
        System.out.println(step + " -> " + LANGUAGE.orElse("<unbound>"));
    }
}
```

Chạy bằng JDK 25:

```shell
javac NestedScopesDemo.java
java NestedScopesDemo
```

Kết quả dự kiến:

```text
0. before -> <unbound>
1. request -> vi-VN
2. export -> en-US
3. appendix -> ja-JP
4. footer -> ja-JP
5. export again -> en-US
6. request again -> vi-VN
7. sibling -> fr-FR
8. after sibling -> vi-VN
9. after -> <unbound>
```

Có thể theo dõi các lớp ngữ cảnh như sau:

```text
Ngoài request: unbound
└── LANGUAGE = vi-VN
    ├── LANGUAGE = en-US
    │   └── LANGUAGE = ja-JP
    │       └── renderFooter() đọc ja-JP
    │   Kết thúc appendix: đọc lại en-US
    ├── Kết thúc export: đọc lại vi-VN
    ├── LANGUAGE = fr-FR
    └── Kết thúc sibling: đọc lại vi-VN
Kết thúc request: unbound
```

Ba điểm cần nhận ra từ ví dụ:

- `renderFooter()` không tự tạo phạm vi nhưng vẫn thấy `ja-JP` vì được gọi trong phạm vi đó.
- Phạm vi `fr-FR` bắt đầu sau khi phạm vi `en-US` đã kết thúc, nên khi nó thoát, giá trị trở lại `vi-VN`.
- Bên ngoài phạm vi ngoài cùng, khóa trở lại trạng thái ban đầu là unbound. Chuỗi `"<unbound>"` chỉ là giá trị dự phòng do ví dụ truyền vào `orElse`, không phải giá trị được bind.

Không cần gọi thao tác gỡ ràng buộc bằng tay. Nếu khóa đã có một ràng buộc trước khi đoạn mã này chạy, khi kết thúc nó sẽ trở về ràng buộc trước đó, thay vì luôn trở thành unbound.

## 4. `call`: trả kết quả ra ngoài mà vẫn kết thúc phạm vi

Dùng `run` cho tác vụ không trả kết quả; dùng `call` khi cần một kết quả. Trong API chính thức của Java 25, tác vụ của `call` có kiểu đích `ScopedValue.CallableOp`, hỗ trợ trả giá trị và ném ngoại lệ. Lambda giúp cách gọi ngắn gọn; xem [API `CallableOp`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.CallableOp.html).

Chương trình `ScopeResultDemo.java`:

```java
public class ScopeResultDemo {
    private static final ScopedValue<String> LANGUAGE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(LANGUAGE, "vi-VN").run(() -> {
            String selected = ScopedValue.where(LANGUAGE, "en-US")
                    .call(() -> {
                        return LANGUAGE.get();
                    });

            System.out.println("result = " + selected);
            System.out.println("current = " + LANGUAGE.get());
        });

        System.out.println("bound = " + LANGUAGE.isBound());
    }
}
```

Kết quả dự kiến:

```text
result = en-US
current = vi-VN
bound = false
```

`return` trong lambda kết thúc tác vụ con và trả chuỗi đã đọc về cho `call`. Khi câu lệnh gán cho `selected` hoàn tất, ràng buộc con đã kết thúc. Việc biến `selected` còn giữ chuỗi `en-US` không kéo dài ràng buộc.

Với phương thức trả về một kết quả tính toán, nguyên tắc vẫn như vậy: dữ liệu kết quả có thể sống lâu hơn phạm vi tính toán; việc đọc `LANGUAGE.get()` về sau dựa trên ngữ cảnh tại lúc đọc.

## 5. Ngoại lệ và vị trí của `catch`, `finally`

### 5.1. Khôi phục xảy ra khi tác vụ con thoát

Một ngoại lệ thoát khỏi tác vụ không làm ràng buộc con tiếp tục tồn tại trong phần xử lý bên ngoài. `run` và `call` khôi phục ràng buộc trước đó rồi truyền ngoại lệ ra ngoài. Đây là hành vi được quy định trong [API `ScopedValue.Carrier`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html#run(java.lang.Runnable)).

Chương trình `ExceptionScopeDemo.java` cố ý tạo lỗi để quan sát điều này:

```java
public class ExceptionScopeDemo {
    private static final ScopedValue<String> LANGUAGE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        try {
            ScopedValue.where(LANGUAGE, "vi-VN").run(() -> {
                try {
                    ScopedValue.where(LANGUAGE, "en-US").run(() -> {
                        try {
                            System.out.println("inner = " + LANGUAGE.get());
                            throw new IllegalStateException("export failed");
                        } finally {
                            System.out.println(
                                    "inner finally = " + LANGUAGE.get());
                        }
                    });
                } catch (IllegalStateException ex) {
                    System.out.println("outer catch = " + LANGUAGE.get());
                    throw ex;
                } finally {
                    System.out.println("outer finally = " + LANGUAGE.get());
                }
            });
        } catch (IllegalStateException ex) {
            System.out.println("outside bound = " + LANGUAGE.isBound());
        }
    }
}
```

Kết quả dự kiến:

```text
inner = en-US
inner finally = en-US
outer catch = vi-VN
outer finally = vi-VN
outside bound = false
```

Trình tự này xuất phát từ hai ranh giới khác nhau:

1. `finally` nằm **trong tác vụ con** chạy khi tác vụ con chưa hoàn tất, nên vẫn thấy `en-US`.
2. Sau khi tác vụ con hoàn tất bằng ngoại lệ, lời gọi `run` con thoát. `catch` nằm trong tác vụ ngoài thấy `vi-VN` đã được khôi phục.
3. `finally` của tác vụ ngoài vẫn chạy trong ràng buộc `vi-VN`.
4. Ngoại lệ tiếp tục ra ngoài lời gọi `run` ngoài cùng; tại đây khóa đã unbound.

Thứ tự xử lý `try`, `catch`, `finally` tuân theo [JLS §14.20.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.2). Điều cần xác định khi đọc mã là `finally` nằm ở bên trong tác vụ nào.

### 5.2. Bắt ngoại lệ ngay trong tác vụ con chưa làm thoát phạm vi

Nếu tác vụ `en-US` tự bắt lỗi rồi tiếp tục chạy, các câu lệnh tiếp theo trong tác vụ đó vẫn đọc `en-US`. Tương tự, `finally` của một `try` nhỏ bên trong tác vụ không tự kết thúc ràng buộc. Ranh giới khôi phục là khi tác vụ được `run` hoặc `call` thực thi thực sự hoàn tất.

| Điểm thực thi | Ngữ cảnh trong ví dụ |
| --- | --- |
| Trong thân tác vụ con | `en-US` |
| Trong `catch` hoặc `finally` còn thuộc tác vụ con | `en-US` |
| Sau lời gọi `run` con, còn trong tác vụ ngoài | `vi-VN` |
| Sau lời gọi `run` ngoài cùng | Unbound |

Việc khôi phục ràng buộc không có nghĩa là lỗi được bỏ qua. Tác vụ vẫn cần chính sách xử lý lỗi phù hợp với nghiệp vụ.

## 6. Che khuất được áp dụng riêng cho từng khóa

Một request thường có nhiều dữ liệu ngữ cảnh, chẳng hạn mã request và ngôn ngữ. Phạm vi con có thể đổi ngôn ngữ mà vẫn giữ mã request.

Chương trình `MultipleKeysDemo.java`:

```java
public class MultipleKeysDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();
    private static final ScopedValue<String> LANGUAGE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-42")
                .where(LANGUAGE, "vi-VN")
                .run(() -> {
                    print("request");

                    ScopedValue.where(LANGUAGE, "en-US")
                            .run(() -> print("export"));

                    print("after export");
                });
    }

    private static void print(String step) {
        System.out.println(step + " -> "
                + REQUEST_ID.get() + " / " + LANGUAGE.get());
    }
}
```

Kết quả dự kiến:

```text
request -> req-42 / vi-VN
export -> req-42 / en-US
after export -> req-42 / vi-VN
```

Ở phạm vi export, `LANGUAGE` được bind lại, còn `REQUEST_ID` vẫn được đọc từ phạm vi ngoài. Mô hình này hữu ích khi thư viện cần một tùy chọn tạm thời nhưng phần ghi log vẫn cần mã request ban đầu.

Khóa được xác định bởi đối tượng `ScopedValue`, không phải tên biến Java. Nếu tạo một `ScopedValue.newInstance()` khác cũng có kiểu `String`, đó là khóa khác. Bind khóa mới không che khuất khóa cũ. Vì vậy, tạo khóa mới bên trong một phương thức không phải cách thay ngữ cảnh của khóa đã được các phương thức khác sử dụng.

## 7. Ứng dụng: thay một phần ngữ cảnh bằng đối tượng mới

Khi nhiều thuộc tính cần đi cùng nhau, có thể gói chúng trong một record bất biến. Phạm vi con tạo một phiên bản mới có tùy chọn khác, còn các thuộc tính nhận diện request được giữ nguyên.

Chương trình `RequestContextDemo.java`:

```java
public class RequestContextDemo {
    private record RequestContext(String requestId, String language) {}

    private static final ScopedValue<RequestContext> CONTEXT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        var incoming = new RequestContext("req-42", "vi-VN");

        ScopedValue.where(CONTEXT, incoming).run(() -> {
            log("start");
            exportInLanguage("en-US");
            log("continue");
        });
    }

    private static void exportInLanguage(String language) {
        RequestContext parent = CONTEXT.get();
        var exportContext = new RequestContext(parent.requestId(), language);

        ScopedValue.where(CONTEXT, exportContext).run(() -> {
            log("export");
            render();
        });
    }

    private static void render() {
        log("render");
    }

    private static void log(String step) {
        RequestContext current = CONTEXT.get();
        System.out.println(step + " -> "
                + current.requestId() + " / " + current.language());
    }
}
```

Kết quả dự kiến:

```text
start -> req-42 / vi-VN
export -> req-42 / en-US
render -> req-42 / en-US
continue -> req-42 / vi-VN
```

Ở đây, một record gồm hai chuỗi giúp tránh việc sửa dữ liệu ngữ cảnh tại chỗ. Nếu record chứa collection hoặc đối tượng có thể thay đổi, cần thiết kế thêm tính bất biến cho các thành phần đó; bản thân việc khai báo record không đóng băng toàn bộ đồ thị đối tượng.

Cách gom dữ liệu thành một khóa cũng làm rõ đơn vị ngữ cảnh: khi bind lại `CONTEXT`, bạn chọn toàn bộ đối tượng ngữ cảnh cho phạm vi con. Bạn phải chủ động mang theo các thuộc tính cần giữ, như `requestId` trong ví dụ.

## 8. Tạo `Carrier` chưa mở phạm vi

Có hai thời điểm riêng biệt:

```java
var english = ScopedValue.where(LANGUAGE, "en-US");
```

Câu lệnh này tạo một `Carrier` chứa ánh xạ. `LANGUAGE.get()` trên luồng hiện tại chưa bị thay đổi bởi việc tạo carrier.

```java
english.run(() -> render());
```

Lời gọi thứ hai mới chạy `render()` trong ràng buộc `en-US`. Khi lời gọi đó kết thúc, luồng trở lại ngữ cảnh có trước lời gọi.

`Carrier` là bất biến: gọi `where` trên carrier trả về carrier mới. Với các khóa `LANGUAGE`, `REQUEST_ID` đã khai báo như ở ví dụ nhiều khóa:

```java
var base = ScopedValue.where(LANGUAGE, "en-US");
var forRequest = base.where(REQUEST_ID, "req-42");

forRequest.run(() -> {
    // Cả LANGUAGE và REQUEST_ID đều được bind trong tác vụ này.
});
```

`base` vẫn giữ ánh xạ ban đầu của nó. Đây là thao tác chuẩn bị một nhóm ánh xạ, không phải mở hai lớp phạm vi động. Chi tiết về tính bất biến và cách tích lũy ánh xạ có trong [API `Carrier.where`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html#where(java.lang.ScopedValue,T)).

Phân biệt này đặc biệt hữu ích khi mã chuẩn bị một tác vụ ở một nơi và thực thi nó ở nơi khác: cần tìm lời gọi `run` hoặc `call` thực sự để xác định thời hạn ràng buộc.

## 9. Giới hạn của việc khôi phục ngữ cảnh

### 9.1. Khôi phục ràng buộc không hoàn tác tác dụng phụ

Khi phạm vi con thoát, thứ được khôi phục là **ràng buộc mà lần đọc khóa nhìn thấy**. Các thao tác như ghi file, gửi request, cập nhật cơ sở dữ liệu hay sửa một collection không tự bị đảo ngược.

Ví dụ, nếu phạm vi ngoài và phạm vi con cùng giữ tham chiếu tới một `ArrayList`, việc thêm phần tử vào list vẫn tồn tại sau khi phạm vi con kết thúc. Scoped Values không tạo bản sao của list và không cung cấp giao dịch để hoàn tác thay đổi.

Vì vậy, để ngữ cảnh dễ suy luận, nên bind dữ liệu bất biến và tạo đối tượng mới khi cần biến thể tạm thời. Cần phân biệt:

- **Ràng buộc có thời hạn:** khóa nhìn thấy một tham chiếu trong khoảng thực thi xác định.
- **Đối tượng bất biến:** nội dung đối tượng không thể bị sửa qua các tham chiếu khác.

Hai đặc tính này hỗ trợ nhau, nhưng không thay thế nhau.

### 9.2. Lambda không tự chụp ràng buộc lúc được tạo

Đoạn sau là một phương thức đặt trong lớp có khóa `LANGUAGE` như các ví dụ trước:

```java
private static Runnable createDeferredTask() {
    return ScopedValue.where(LANGUAGE, "en-US")
            .call(() -> (Runnable) () ->
                    System.out.println(LANGUAGE.orElse("<unbound>")));
}
```

Nếu gọi theo trình tự:

```java
Runnable task = createDeferredTask();
task.run();
```

và luồng không có ràng buộc khác, kết quả dự kiến là:

```text
<unbound>
```

Tác vụ trả về chỉ chứa hành vi đọc khóa khi nó chạy. Ràng buộc `en-US` đã kết thúc khi `createDeferredTask()` trả về. Nếu chạy cùng tác vụ đó trong một phạm vi `vi-VN`, nó sẽ đọc `vi-VN`.

Nếu cần giữ một dữ liệu cho công việc về sau, hãy lấy dữ liệu cần dùng làm đầu vào rõ ràng, hoặc chủ động mở một phạm vi mới khi thực thi công việc. Việc giữ lại một đối tượng kết quả, một lambda hay một carrier không kéo dài lần ràng buộc đã kết thúc.

### 9.3. Chuyển sang luồng khác cần cơ chế truyền ngữ cảnh phù hợp

Các ví dụ trong bài theo dõi chuỗi gọi đồng bộ trên cùng luồng. Không nên suy ra rằng gửi tác vụ vào executor, dùng `CompletableFuture` hoặc tự tạo một thread sẽ tự mang theo ràng buộc của bên gửi.

`StructuredTaskScope` có cơ chế kế thừa được quy định riêng: nó ghi nhận ràng buộc khi mở scope và các luồng chạy subtask kế thừa ngữ cảnh đó. Subtask có thể mở một phạm vi con để bind lại khóa; khi phạm vi con thoát, nó trở về giá trị đã kế thừa. Trên JDK 25, `StructuredTaskScope` vẫn là preview, dù `ScopedValue` đã chính thức. Xem phần [kế thừa scoped values trong `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#Inheritance).

Khi chưa dùng cơ chế truyền ngữ cảnh được API hoặc framework xác định rõ, hãy coi việc đổi luồng là một ranh giới cần xử lý riêng. Không suy luận vòng đời của tác vụ bất đồng bộ chỉ từ vị trí các dấu ngoặc trong mã nguồn.

## 10. Cách áp dụng trong mã ứng dụng

Khi cần một ngữ cảnh tạm thời, hãy xác định lần lượt:

1. **Khóa nào cần thay?** Dùng lại chính đối tượng khóa mà các phương thức bên dưới đọc.
2. **Phần xử lý nào cần thấy giá trị mới?** Đặt lời gọi đó trong tác vụ của `run` hoặc `call`.
3. **Ngữ cảnh nào phải được giữ?** Với nhiều khóa, chỉ bind lại khóa cần thay; với một record ngữ cảnh, tạo bản mới và giữ các thuộc tính cần thiết.
4. **Điểm đọc nằm trong hay ngoài tác vụ con?** Đặc biệt kiểm tra vị trí `catch`, `finally` và callback được gọi muộn.
5. **Có tác dụng phụ hoặc chuyển luồng không?** Những việc này cần chính sách riêng ngoài cơ chế khôi phục ràng buộc.

Ví dụ với bước xuất tài liệu, phạm vi `en-US` nên bao trọn quá trình dựng nội dung và các lời gọi hỗ trợ cần ngôn ngữ đó. Sau khi bước xuất hoàn tất, phần xử lý request tiếp tục trong `vi-VN`. Nếu có ngoại lệ, phần xử lý lỗi bên ngoài bước xuất đọc lại ngữ cảnh request đã được khôi phục.

Khi đọc một lời gọi `get()`, câu hỏi quyết định là: **trên luồng đang thực thi, ràng buộc gần nhất còn hiệu lực của chính khóa này là gì?** Từ đó có thể xác định giá trị trong phạm vi con, khi quay về phạm vi cha và sau khi thoát toàn bộ chuỗi ràng buộc.
