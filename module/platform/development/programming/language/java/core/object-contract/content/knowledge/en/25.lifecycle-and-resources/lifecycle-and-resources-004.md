# Không dùng finalizer làm cơ chế bắt buộc để giải phóng tài nguyên

## Mục tiêu

Sau bài này, bạn có thể phân biệt việc thu hồi **bộ nhớ heap** với việc giải phóng **tài nguyên bên ngoài heap**; giải thích vì sao `finalize()` không bảo đảm đóng tài nguyên; và thiết kế vòng đời tài nguyên bằng `AutoCloseable`, `try-with-resources` cùng quy tắc sở hữu rõ ràng.

## 1. Bộ thu gom rác không thay thế thao tác đóng tài nguyên

Garbage collector (GC) quản lý tính khả dụng của đối tượng và thu hồi bộ nhớ Java khi phù hợp. Nhưng file descriptor, socket, kết nối cơ sở dữ liệu, native handle, stream I/O và nhiều tài nguyên hệ điều hành có vòng đời, hạn mức riêng. Một đối tượng wrapper không còn được dùng **không đồng nghĩa** với việc tài nguyên mà nó đại diện đã được giải phóng kịp thời.

Ví dụ: chương trình mở nhiều file mà không đóng có thể hết file descriptor ngay cả khi heap còn rất nhiều bộ nhớ. Mục tiêu của quản lý tài nguyên là xác định *ai sở hữu tài nguyên và thời điểm kết thúc sử dụng*, thay vì đợi GC đoán được lúc nào nên dọn.

## 2. `finalize()` hoạt động thế nào và vì sao không được dựa vào nó?

Trong mô hình finalization cũ, lớp có thể ghi đè `protected void finalize() throws Throwable`. Khi một đối tượng đủ điều kiện được thu gom, JVM *có thể* xử lý finalizer của nó. Đây không phải lời hứa rằng phương thức sẽ chạy ngay, sẽ chạy trước thời hạn nào, hoặc sẽ chạy trước khi tiến trình kết thúc.

`Object.finalize()` đã bị đánh dấu deprecated từ Java 9; **JEP 421 (JDK 18)** đánh dấu finalization để loại bỏ trong tương lai. Phần mềm cần hoạt động đúng ngay cả khi finalization bị vô hiệu hóa hoặc không được gọi.

Các vấn đề chính:

- **Không xác định thời điểm:** việc đối tượng trở nên unreachable và việc GC/finalizer xử lý nó không tuân theo thời điểm nghiệp vụ cần đóng file hay connection. `System.gc()` chỉ là yêu cầu và không biến finalizer thành cơ chế đáng tin.
- **Không bảo đảm thực thi:** GC có thể chưa chạy, finalizer có thể bị trì hoãn vô hạn, môi trường có thể tắt finalization, hoặc JVM kết thúc trước khi cleanup xảy ra.
- **Thứ tự và tương tác khó kiểm soát:** tài nguyên liên quan có thể đã ở trạng thái khác; xử lý trên luồng finalization riêng làm việc đồng bộ và lỗi khó dự đoán.
- **Chi phí và rủi ro:** finalizer có thể làm chậm thu hồi bộ nhớ, kéo dài vòng đời đối tượng, và tạo bề mặt lỗi/bảo mật. Một finalizer còn có khả năng làm đối tượng sống lại (object resurrection), khiến việc suy luận vòng đời phức tạp.
- **Lỗi khó quan sát:** ngoại lệ không bắt được trong finalizer không tạo ra cơ chế báo lỗi cleanup giống lời gọi `close()` trực tiếp tại nơi sở hữu tài nguyên.

**Quy tắc:** không viết `finalize()` để thực hiện công việc bắt buộc như flush dữ liệu, commit/rollback, đóng socket, trả connection về pool hay giải phóng native handle. Việc bắt buộc phải hoàn tất phải nằm trong luồng thực thi được kiểm soát.

## 3. Cách làm chính: buộc chủ sở hữu kết thúc vòng đời

Thay một finalizer bằng `close()` chỉ đúng khi **bên sở hữu thực sự gọi** phương thức ấy. Với tài nguyên thuộc phạm vi ngắn, `AutoCloseable` cùng `try-with-resources` giúp Java cố gắng đóng dù phần thân thành công hay ném lỗi:

```java
try (var writer = java.nio.file.Files.newBufferedWriter(path)) {
    writer.write("Xin chào");
}
```

Đoạn minh họa giả định `path` là `Path`, các ngoại lệ `IOException` được khai báo hoặc xử lý. `close()` phải giải phóng tài nguyên thật, và lỗi đóng phải được quan sát; `try-with-resources` giữ lỗi chính của thân `try` và gắn lỗi `close()` thành suppressed exception qua `getSuppressed()`. Các tài nguyên khai báo theo thứ tự A rồi B sẽ được đóng B trước A.

Bài tiếp theo về `AutoCloseable` cung cấp chương trình chạy được, ví dụ đọc/ghi file và JDBC, kiểm chứng thứ tự đóng cùng đường lỗi kép. Ở đây trọng tâm là **thiết kế lại quyền sở hữu và điểm đóng** khi bỏ finalizer, không chỉ thay tên callback.

## 4. Thiết kế lớp tự quản lý tài nguyên

Khi tự bọc native handle, socket hoặc đối tượng cần đóng, hãy triển khai `AutoCloseable` (hoặc `Closeable` nếu phù hợp với hợp đồng I/O):

1. Xác định đối tượng nào **sở hữu** tài nguyên và ai phải gọi `close()`. Nếu thư viện/framework/pool sở hữu tài nguyên, không tự ý đóng đối tượng mượn.
2. Làm rõ trạng thái **đang mở / đã đóng**; sau `close()`, từ chối thao tác không hợp lệ. Tùy loại tài nguyên, thiết kế `close()` an toàn khi gọi lặp lại.
3. Giải phóng tài nguyên thực sự trong `close()`, thông báo lỗi thích hợp. Khi cleanup có thể thất bại, cố gắng giải phóng những phần còn lại và quản lý ngoại lệ một cách có chủ ý.
4. Chuyển quyền sở hữu một cách minh bạch nếu trả tài nguyên ra khỏi phạm vi hiện tại. Không đóng tài nguyên còn được thành phần khác sử dụng.
5. Nếu dùng tài nguyên qua nhiều luồng, quy định rõ an toàn luồng và đồng bộ trạng thái `close()`/sử dụng; một cờ `boolean` đơn giản không tự bảo đảm thread safety.

Ví dụ chỉ **mô phỏng vòng đời**, không mở native handle thật:

```java
// OwnershipDemo.java
public class OwnershipDemo {
    static final class ManagedResource implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) {
                throw new IllegalStateException("Tài nguyên đã đóng");
            }
            System.out.println("Đang sử dụng");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("Đã đóng");
            }
        }
    }

    public static void main(String[] args) {
        try (ManagedResource resource = new ManagedResource()) {
            resource.use();
        }
    }
}
```

```bash
javac OwnershipDemo.java
java OwnershipDemo
```

```text
Đang sử dụng
Đã đóng
```

Ở triển khai thực tế, đặt lệnh giải phóng file/socket/native handle bên trong `close()`; không nhầm câu `System.out.println("Đã đóng")` ở ví dụ với thao tác giải phóng thật. Với tài nguyên cần thread safety, đồng bộ hoặc dùng cơ chế trạng thái nguyên tử phù hợp.

## 5. Cleaner không biến cleanup dự phòng thành bắt buộc

Có thể đăng ký `Cleaner` cho wrapper native handle nếu cần giảm hậu quả người dùng quên `close()`, nhưng action chỉ tự động chạy khi điều kiện reachability và lịch xử lý cho phép. Luồng nghiệp vụ vẫn phải đóng chủ động; action phải tách khỏi đối tượng được theo dõi và chống giải phóng hai lần. Không đặt flush, commit/rollback hoặc thông báo bắt buộc trong callback Cleaner. Bài cuối chương hướng dẫn mô hình `Cleanable` và kiểm thử giới hạn này.

## 6. Chuyển từ code dùng finalizer sang quản lý tài nguyên rõ ràng

Giả sử code cũ dựa vào `finalize()` để đóng một handle. Lộ trình sửa đúng:

1. Tìm các override `finalize()`, tài nguyên được giải phóng bên trong, và những nơi khởi tạo đối tượng. Kiểm tra cả dependency có liên quan.
2. Bổ sung `close()`/ `AutoCloseable`, tách logic cleanup thành thao tác rõ ràng với quy tắc chống đóng lặp; bỏ phụ thuộc nghiệp vụ vào finalizer.
3. Đổi bên **sở hữu** đối tượng sang `try-with-resources` khi vòng đời theo phạm vi, hoặc gọi `close()` tại điểm đóng của service/component khi vòng đời dài hơn.
4. Kiểm thử đường đi bình thường, ngoại lệ khi đang dùng, ngoại lệ khi đóng, gọi đóng nhiều lần và việc dùng sau khi đóng. Xác minh tài nguyên thực được giải phóng mà **không gọi `System.gc()`**.
5. Cân nhắc Cleaner chỉ để giảm thiểu rò rỉ do người gọi quên đóng đối với những tài nguyên phù hợp; không coi nó là đường cleanup chính.

Đoạn minh họa ý tưởng cần tránh:

```java
// Mã cũ, không nên áp dụng: cố ý chỉ là fragment minh họa.
@Override
protected void finalize() throws Throwable {
    releaseNativeHandle();
}
```

Thiết kế nên dùng: đối tượng sở hữu handle triển khai `AutoCloseable`, gọi `releaseNativeHandle()` từ `close()` và buộc nơi tạo/sở hữu đối tượng kết thúc sử dụng bằng `try-with-resources` hoặc `close()` tường minh. Phương thức `releaseNativeHandle()` ở fragment trên là tên giả định minh họa, không phải Java API.

## 7. Các lỗi thường gặp

| Quan niệm hoặc cách làm | Vấn đề | Cách thay thế |
| --- | --- | --- |
| “GC sẽ tự đóng file/connection” | Bộ nhớ được thu hồi và tài nguyên hệ điều hành được đóng là hai trách nhiệm khác nhau | Đóng đúng hạn qua `try-with-resources` |
| Gọi `System.gc()` sau khi dùng tài nguyên | Không bảo đảm GC hay finalizer chạy đúng lúc | Gọi `close()` tại ranh giới sở hữu |
| Dùng `finalize()` để flush, commit hoặc rollback | Những thao tác này cần kiểm soát thứ tự, lỗi và thời điểm | Thực hiện chủ động ở luồng nghiệp vụ |
| Chỉ cài `Cleaner`, không có `close()` | Cleaner tự động vẫn không có thời hạn bảo đảm | `close()` là chính; Cleaner chỉ dự phòng |
| Dựa vào shutdown hook để đóng từng đối tượng | Hook thuộc vòng đời tiến trình, có thể không chạy trong mọi kiểu kết thúc, không quản lý vòng đời mỗi tài nguyên | Đóng ngay khi không còn sử dụng |
| Đóng tài nguyên do framework/pool sở hữu | Có thể làm hỏng đối tượng đang được chia sẻ hoặc tái sử dụng | Theo đúng hợp đồng sở hữu của API |

## 8. Tự kiểm tra

- Khi một `Socket` không còn được tham chiếu, có thể kết luận ngay socket đã được đóng không? **Không.** Mất tham chiếu không bảo đảm cleanup hệ điều hành được thực hiện kịp thời.
- Khi thân `try-with-resources` và `close()` đều ném exception, tìm lỗi đóng ở đâu? **`Throwable.getSuppressed()`** trên ngoại lệ chính.
- Có được dùng Cleaner để chắc chắn flush dữ liệu trước khi trả HTTP response không? **Không.** Hãy flush/close tường minh trong luồng xử lý có kiểm soát.
- Một lớp không nắm giữ file/socket/native handle có cần finalizer để GC giải phóng heap không? **Không.** GC tự quản lý bộ nhớ của các đối tượng thông thường.

**Ghi nhớ:** vòng đời tài nguyên cần thiết kế theo **quyền sở hữu + thao tác đóng rõ ràng**. Finalizer và các callback phụ thuộc GC không đáp ứng cam kết giải phóng tài nguyên tại thời điểm bắt buộc.

## Tài liệu tham khảo

- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 17 — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html)
