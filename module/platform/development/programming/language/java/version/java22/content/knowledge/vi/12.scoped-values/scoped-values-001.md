# Từ JEP 464 trong Java 22 tới Scoped Values chính thức từ JDK 25

`ScopedValue` là API trong `java.lang` dùng để truyền dữ liệu theo một chiều từ nơi bắt đầu xử lý tới các phương thức được gọi trong cùng luồng thực thi. Dữ liệu chỉ được gắn với một phạm vi thực thi có giới hạn; khi phạm vi kết thúc, binding tự động được khôi phục hoặc được gỡ bỏ. Cách làm này phù hợp với những ngữ cảnh như mã yêu cầu, người dùng hiện tại, tenant, locale và thông tin truy vết.

JEP 464 đưa Scoped Values vào Java 22 ở vòng preview thứ hai. Sau các vòng preview tiếp theo, JEP 506 hoàn thiện API trong JDK 25. Vì vậy, khi viết ứng dụng Java hiện đại, hãy dùng API đã hoàn thiện trong JDK 25 trở lên làm chuẩn. Các ví dụ dưới đây sử dụng API chính thức, không yêu cầu bật preview.

## 1. Vấn đề Scoped Values giải quyết

Thông thường, dữ liệu được truyền qua tham số phương thức. Cách này rõ ràng và nên được ưu tiên khi các phương thức thực sự cần biết dữ liệu đó. Tuy nhiên, trong một chuỗi gọi sâu, có thể chỉ phương thức ở đầu và một callback ở cuối cần thông tin; các phương thức trung gian phải nhận rồi chuyển tiếp tham số dù không sử dụng nó.

Ví dụ, một yêu cầu HTTP đi qua controller, service, repository và cuối cùng gọi một thư viện ghi log. Thông tin `requestId` có ích ở nhiều điểm, nhưng việc thêm tham số `requestId` vào mọi phương thức trung gian làm chữ ký phương thức phình to và buộc nhiều lớp phụ thuộc vào chi tiết của ngữ cảnh yêu cầu.

`ThreadLocal` thường được dùng để giải quyết tình huống này bằng cách gắn dữ liệu với từng thread. Cách đó có thể phù hợp với trạng thái thực sự thuộc về thread, nhưng có một số điểm cần quản lý:

- Giá trị có thể tồn tại sau khi tác vụ kết thúc nếu mã không gọi `remove()` đúng lúc. Điều này đặc biệt dễ gây rò rỉ ngữ cảnh khi thread được tái sử dụng trong thread pool.
- Mã ở bất kỳ vị trí nào có quyền truy cập `ThreadLocal` đều có thể thay đổi giá trị, dù mục đích ban đầu chỉ là truyền thông tin từ caller xuống callee.
- Việc kế thừa trạng thái thread-local khi tạo thread con có chi phí sao chép dữ liệu.

Scoped Values hướng tới trường hợp truyền dữ liệu một chiều, có phạm vi và thường không thay đổi. Caller thiết lập binding trước khi gọi một tác vụ; các phương thức được gọi bên trong có thể đọc binding mà không cần nhận thêm tham số. Khi tác vụ kết thúc, kể cả khi có exception, binding tự động trở về trạng thái trước đó.

## 2. Từ JEP 464 đến API chính thức

Scoped Values được phát triển qua nhiều giai đoạn để hoàn thiện thiết kế và API:

| Phiên bản JDK | JEP | Trạng thái |
| --- | --- | --- |
| JDK 22 | JEP 464 | Preview lần thứ hai; đây là mốc của bài học này. |
| JDK 23 | JEP 481 | Preview lần thứ ba. |
| JDK 24 | JEP 487 | Preview lần thứ tư. |
| JDK 25 | JEP 506 | API được hoàn thiện và trở thành tính năng chính thức. |

Điểm quan trọng khi đọc tài liệu cũ là phân biệt mã preview của JDK 22–24 với API đã hoàn thiện trong JDK 25. Các ví dụ trong bài này chỉ dùng API JDK 25. Với JDK 25 trở lên, `ScopedValue` là API chuẩn và không cần tùy chọn `--enable-preview` để sử dụng riêng tính năng này.

## 3. Các thành phần chính của API

`ScopedValue<T>` đại diện cho một khóa có kiểu `T`. Khóa được tạo bằng `ScopedValue.newInstance()` và ban đầu chưa được bind ở bất kỳ thread nào. Trong thực tế, khóa thường được khai báo là `private static final` để giới hạn nơi có thể truy cập nó.

| API | Vai trò |
| --- | --- |
| `ScopedValue.newInstance()` | Tạo một khóa Scoped Value mới, ban đầu chưa được bind. |
| `ScopedValue.where(key, value)` | Tạo một `ScopedValue.Carrier` chứa binding giữa khóa và giá trị. |
| `Carrier.run(Runnable)` | Chạy một tác vụ không trả về kết quả trong phạm vi binding. |
| `Carrier.call(ScopedValue.CallableOp)` | Chạy một tác vụ có trả về kết quả trong phạm vi binding. |
| `ScopedValue.get()` | Đọc giá trị đang được bind cho thread hiện tại. |
| `ScopedValue.isBound()` | Kiểm tra khóa có đang được bind trong thread hiện tại hay không. |
| `ScopedValue.orElse(value)` | Đọc giá trị nếu đã bind, nếu chưa thì trả về giá trị mặc định. |
| `ScopedValue.orElseThrow(supplier)` | Đọc giá trị nếu đã bind, nếu chưa thì ném exception do supplier tạo ra. |

`where` trả về `Carrier`, không trực tiếp thực thi tác vụ. `Carrier` là một ánh xạ bất biến và an toàn khi dùng đồng thời. Có thể gọi tiếp `where` trên carrier để thêm binding trước khi chạy tác vụ. Phương thức `run` và `call` xác định ranh giới của phạm vi động.

### Ví dụ: truyền request context qua chuỗi gọi

Ví dụ sau dùng một `record` bất biến để gom các thông tin liên quan đến request vào cùng một giá trị:

```java
public final class RequestExample {
    private static final ScopedValue<RequestContext> CURRENT_REQUEST =
            ScopedValue.newInstance();

    record RequestContext(String requestId, String userId) {}

    public static void main(String[] args) {
        var context = new RequestContext("req-42", "user-17");

        ScopedValue.where(CURRENT_REQUEST, context)
                .run(RequestExample::handleRequest);
    }

    private static void handleRequest() {
        loadOrder();
    }

    private static void loadOrder() {
        RequestContext context = CURRENT_REQUEST.get();
        System.out.printf("request=%s, user=%s%n",
                context.requestId(), context.userId());
    }
}
```

`main` bind `CURRENT_REQUEST` với context rồi gọi `handleRequest`. `handleRequest` không cần nhận hay chuyển tiếp context nhưng `loadOrder` vẫn đọc được giá trị qua `CURRENT_REQUEST.get()`. Khóa được khai báo `private`, nên chỉ mã nằm trong phạm vi truy cập phù hợp mới có thể đọc nó.

`ScopedValue` thuộc package `java.lang`, vì vậy không cần câu lệnh `import` riêng. Ví dụ có thể biên dịch và chạy bằng JDK 25 trở lên.

### Nhiều binding trong cùng một phạm vi

Khi cần truyền một vài giá trị độc lập, có thể nối nhiều lời gọi `where`:

```java
public final class MultiBindingExample {
    private static final ScopedValue<String> USER_ID = ScopedValue.newInstance();
    private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(USER_ID, "user-17")
                .where(REQUEST_ID, "req-42")
                .run(MultiBindingExample::handleRequest);
    }

    private static void handleRequest() {
        System.out.printf("user=%s, request=%s%n", USER_ID.get(), REQUEST_ID.get());
    }
}
```

Trong `handleRequest` và các phương thức được gọi bên trong, cả hai khóa đều có thể được đọc bằng `get()`. Mỗi lời gọi `where` tạo ra một carrier mới với ánh xạ được bổ sung; carrier trước đó không bị thay đổi.

Nếu ngữ cảnh có nhiều trường liên quan, nên gom chúng vào một kiểu dữ liệu bất biến, chẳng hạn `record RequestContext`, rồi bind một Scoped Value duy nhất. Cách này giúp mã dễ đọc và phù hợp với thiết kế cache nội bộ của Scoped Values, vốn được tối ưu cho số lượng khóa tương đối nhỏ.

## 4. Phạm vi động và binding lồng nhau

Binding tồn tại trong suốt thời gian tác vụ được thực thi bởi `run` hoặc `call`. Khi tác vụ kết thúc bình thường hoặc ném exception, binding được gỡ bỏ; nếu khóa đã có binding ở phạm vi bên ngoài thì giá trị trước đó được khôi phục.

Việc bind lại cùng một khóa trong một phạm vi lồng nhau được gọi là *rebinding*:

```java
public final class RebindingExample {
    private static final ScopedValue<String> TENANT = ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "tenant-A").run(() -> {
            printTenant(); // tenant-A

            ScopedValue.where(TENANT, "tenant-B")
                    .run(() -> printTenant()); // tenant-B

            printTenant(); // tenant-A được khôi phục
        });
    }

    private static void printTenant() {
        System.out.println(TENANT.get());
    }
}
```

Phạm vi bên trong tạm thời nhìn thấy `tenant-B`. Khi phạm vi đó kết thúc, phạm vi bên ngoài tiếp tục nhìn thấy `tenant-A`. Không cần tự lưu giá trị cũ hoặc gọi thao tác dọn dẹp.

Nếu gọi `get()` khi khóa chưa được bind trong thread hiện tại, Java ném `NoSuchElementException`. Khi việc không có binding là một trạng thái hợp lệ, hãy kiểm tra `isBound()` hoặc dùng `orElse()`; nếu binding bắt buộc phải tồn tại, `get()` giúp phát hiện lỗi sớm.

`call` dùng khi tác vụ cần trả về kết quả:

```java
public final class CallExample {
    private static final ScopedValue<String> USER_ID = ScopedValue.newInstance();

    public static void main(String[] args) throws Exception {
        String greeting = ScopedValue.where(USER_ID, "user-17")
                .call(() -> "Hello, " + USER_ID.get());
        System.out.println(greeting);
    }
}
```

`call` trả về kết quả của tác vụ và vẫn khôi phục binding khi tác vụ hoàn tất. Kiểu hàm `ScopedValue.CallableOp` cho phép tác vụ ném exception; exception được truyền trở lại caller.

## 5. Scoped Values và đa luồng

Binding của Scoped Value là theo từng thread. Hai thread có thể cùng dùng một khóa nhưng nhìn thấy các giá trị được bind riêng trong từng thread.

Scoped Values cũng hỗ trợ chia sẻ ngữ cảnh trong mô hình đa luồng có cấu trúc. Khi tạo `StructuredTaskScope` bên trong một phạm vi Scoped Value, các binding tại thời điểm tạo scope được capture và kế thừa bởi những thread con được khởi chạy bằng `fork`. Các thread con có thể đọc cùng ngữ cảnh mà không phải truyền từng giá trị qua tham số.

Có một điểm cần phân biệt theo phiên bản: trong JDK 25, Scoped Values đã là API chính thức, còn Structured Concurrency vẫn là preview theo JEP 505. Vì vậy, việc dùng riêng `ScopedValue` không cần bật preview; phần mã sử dụng `StructuredTaskScope` vẫn chịu yêu cầu preview của Structured Concurrency trong JDK 25. Không nên giả định binding tự động truyền sang mọi thread được tạo tùy ý hoặc mọi tác vụ gửi vào executor.

Việc bind một giá trị không làm cho đối tượng được bind trở thành bất biến. Nếu giá trị được chia sẻ giữa nhiều thread, hãy dùng đối tượng bất biến hoặc bảo vệ mọi thao tác truy cập bằng cơ chế đồng bộ phù hợp. `record` với các thành phần bất biến là lựa chọn thuận tiện cho các context thường gặp.

## 6. So sánh ScopedValue với ThreadLocal

| Khía cạnh | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Vòng đời | Gắn với phạm vi thực thi `run`/`call`; tự khôi phục khi thoát phạm vi. | Gắn với thread; cần quản lý vòng đời và thường phải gọi `remove()` khi dùng thread pool. |
| Hướng truyền dữ liệu | Phù hợp truyền một chiều từ caller xuống callee. | Có thể đọc và thay đổi từ nhiều vị trí có quyền truy cập. |
| Thay đổi binding | Được thiết lập qua `where`; phạm vi lồng nhau có thể bind lại và tự khôi phục. | Có thể thay đổi bằng `set()` và xóa bằng `remove()`. |
| Chia sẻ với thread con | Hỗ trợ trong các cấu trúc có phạm vi rõ ràng như `StructuredTaskScope`. | `ThreadLocal` thông thường không tự kế thừa; `InheritableThreadLocal` có cơ chế riêng. |
| Trường hợp phù hợp | Ngữ cảnh bất biến, chỉ cần truyền xuống các lời gọi sâu. | Trạng thái thực sự thuộc về thread và cần thay đổi trong suốt vòng đời của thread. |

Scoped Values không phải lựa chọn thay thế cho mọi `ThreadLocal`. Hãy chọn theo mục đích: nếu cần truyền context một chiều trong một tác vụ có ranh giới rõ ràng, ưu tiên Scoped Values; nếu cần trạng thái mutable gắn với thread, `ThreadLocal` vẫn có thể phù hợp khi quản lý vòng đời cẩn thận.

## 7. Nguyên tắc sử dụng trong ứng dụng hiện đại

1. **Bind ở ranh giới xử lý.** Thiết lập context khi bắt đầu xử lý request hoặc tác vụ, sau đó để các phương thức bên trong đọc khi cần.
2. **Giữ khóa ở phạm vi truy cập hẹp.** Khai báo khóa `private static final` khi có thể. Đối tượng `ScopedValue` đóng vai trò như một capability: ai có tham chiếu tới khóa mới có thể đọc binding của khóa đó.
3. **Ưu tiên giá trị bất biến.** Scoped Values giới hạn vòng đời của binding, nhưng không ngăn đối tượng được bind bị sửa đổi.
4. **Gom context hợp lý.** Nếu nhiều trường luôn đi cùng nhau, tạo một `record` hoặc kiểu dữ liệu bất biến tương đương và bind một khóa thay vì tạo quá nhiều khóa riêng lẻ.
5. **Không đọc ngoài phạm vi.** Dùng `get()` khi binding là điều kiện bắt buộc; dùng `isBound()` hoặc `orElse()` khi chương trình chấp nhận trường hợp chưa có binding.
6. **Kiểm tra ranh giới khi xử lý lỗi và chạy đồng thời.** Bảo đảm tác vụ luôn đi qua `run`/`call`; nếu chia sẻ context qua thread con, chỉ dựa vào cơ chế kế thừa được hỗ trợ và giữ dữ liệu an toàn khi truy cập đồng thời.

Scoped Values đặc biệt hữu ích cho request ID, principal bảo mật, tenant ID, locale và dữ liệu tracing. Chúng giúp giảm việc chuyển tiếp tham số qua các lớp trung gian, đồng thời làm cho thời điểm bắt đầu và kết thúc của ngữ cảnh trở nên rõ ràng trong mã nguồn.

## Tài liệu tham khảo

- [JEP 464: Scoped Values (Second Preview)](https://openjdk.org/jeps/464) — trạng thái của tính năng trong JDK 22.
- [JEP 481: Scoped Values (Third Preview)](https://openjdk.org/jeps/481) — vòng preview trong JDK 23.
- [JEP 487: Scoped Values (Fourth Preview)](https://openjdk.org/jeps/487) — vòng preview trong JDK 24.
- [JEP 506: Scoped Values](https://openjdk.org/jeps/506) — hoàn thiện tính năng trong JDK 25.
- [ScopedValue, Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html) — API và ngữ nghĩa binding.
- [ScopedValue.Carrier, Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html) — `where`, `run` và `call`.
- [JEP 505: Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505) — trạng thái preview của Structured Concurrency trong JDK 25.
