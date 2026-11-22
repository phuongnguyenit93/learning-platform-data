# `Object.finalize()` đã bị đánh dấu `deprecated for removal`

## 1. Khái niệm và trạng thái API

`java.lang.Object` là lớp gốc của hệ phân cấp lớp Java. Nó từng cung cấp phương thức:

```java
@Deprecated(since = "9", forRemoval = true)
protected void finalize() throws Throwable
```

- `finalize()` là **finalizer**: cơ chế cũ cho phép một lớp định nghĩa thao tác khi JVM xử lý đối tượng không còn được chương trình truy cập, trước khi thu hồi bộ nhớ của đối tượng đó.
- Bản triển khai `Object.finalize()` mặc định **không làm gì**. Trước đây, một số lớp ghi đè phương thức để giải phóng tài nguyên ngoài heap như file descriptor, socket hoặc native handle.
- API được đánh dấu deprecated từ **Java 9**; **JEP 421 (JDK 18)** đánh dấu cơ chế finalization là *deprecated for removal*. Tại Java SE 26, `Object.finalize()` vẫn còn trong API nhưng được ghi rõ có thể bị loại bỏ trong phiên bản sau.
- `@Deprecated(forRemoval = true)` là tín hiệu cần di chuyển khỏi API; nó **không đồng nghĩa phương thức đã bị xóa ngay** hoặc mã hiện tại chắc chắn không biên dịch.

Điều cần nhớ: **Không dùng `finalize()` để quản lý tài nguyên trong mã Java mới; hãy đóng tài nguyên một cách chủ động.**

## 2. Finalization hoạt động thế nào và vì sao không đáng tin

Diễn tiến khái quát khi finalization đang được JVM bật:

1. Một đối tượng có finalizer không còn được tham chiếu theo cách khiến chương trình sử dụng nó nữa.
2. Garbage collector (GC) có thể nhận diện đối tượng đủ điều kiện finalization và JVM có thể sắp lịch thực thi finalizer.
3. Finalizer, nếu được gọi, chạy bằng luồng không do ứng dụng trực tiếp lựa chọn. Sau đó, GC còn cần kiểm tra lại khả năng truy cập đối tượng trước khi thu hồi bộ nhớ.

**Không có cam kết finalizer chạy ngay, chạy trước khi JVM kết thúc, hay chạy trước một thời hạn cụ thể.** Một đối tượng có thể không được finalization trong suốt thời gian chương trình hoạt động. Gọi `System.gc()` hay `System.runFinalization()` không biến việc dọn dẹp thành hợp đồng bảo đảm.

Các vấn đề cốt lõi:

| Vấn đề | Hệ quả |
| --- | --- |
| Thời điểm không xác định | File descriptor, socket hoặc bộ nhớ native có thể bị giữ lâu dù đối tượng Java không còn được dùng. |
| Chi phí GC và lưu giữ đối tượng | Đối tượng cần finalization có thể phải đi qua quá trình xử lý bổ sung trước khi bộ nhớ được thu hồi. |
| Rủi ro bảo mật | Finalizer có thể truy cập trạng thái đối tượng chưa được khởi tạo hoàn chỉnh hoặc làm đối tượng “sống lại” (*object resurrection*). |
| Khó kiểm soát lỗi và đồng thời | Finalizer chạy trên luồng không xác định; ngoại lệ không được bắt trong finalizer bị bỏ qua. |
| Khó kiểm thử | Kết quả phụ thuộc GC, thời điểm thực thi và trạng thái JVM; bài test có thể lúc qua lúc trượt. |

Đối với một đối tượng, JVM không tự gọi finalizer quá một lần; điều đó vẫn **không bảo đảm sẽ có một lần nào** trước khi chương trình dừng. GC quản lý **bộ nhớ heap**, không tự biết khi nào nghiệp vụ đã sử dụng xong mọi tài nguyên hệ điều hành.

## 3. Những tên gần giống nhưng khác bản chất

- `finalize()`: callback dọn dẹp kiểu cũ gắn với vòng đời đối tượng và GC; đã deprecated for removal.
- `finally`: khối lệnh của `try/catch/finally`, thực thi khi luồng điều khiển rời `try` theo các quy tắc thông thường; có thể dùng để gọi `close()`.
- `final`: từ khóa cấm gán lại biến, ghi đè phương thức hoặc kế thừa lớp tùy ngữ cảnh; không liên quan đến finalizer.
- `close()` và `AutoCloseable`: giao diện quản lý vòng đời tài nguyên theo chủ ý của người gọi, thường kết hợp `try-with-resources`.

## 4. Giải pháp khi mã cần đóng tài nguyên

Khi một lớp sở hữu file, socket, kết nối hoặc handle cần đóng đúng hạn, cho lớp thực hiện `AutoCloseable` và tổ chức bên sử dụng gọi `close()` tại ranh giới sở hữu; cách thông dụng nhất là `try-with-resources`. Java gọi `close()` khi rời khối trong luồng thực thi bình thường, kể cả khi thân khối ném ngoại lệ. Đây là hợp đồng theo luồng điều khiển, không phải một tác dụng phụ của GC.

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
```

Đây là đoạn minh họa nằm trong phương thức có biến `path` kiểu `Path`, với ngoại lệ `IOException` được xử lý hoặc khai báo phù hợp. Bài chuyên sâu về `AutoCloseable` phân tích thứ tự đóng, ownership và suppressed exceptions.

## 5. Cleaner chỉ có vai trò dự phòng

`java.lang.ref.Cleaner` (Java 9+) cho phép đăng ký một cleaning action độc lập và gọi `Cleanable.clean()` chủ động. Khi chỉ dựa vào GC kích hoạt, hành động này **không có hạn chót** và có thể không chạy trước lúc JVM thoát. Không dùng Cleaner để thay thế `close()` hoặc để commit, flush dữ liệu bắt buộc. Nếu dùng cho native handle, action không được giữ tham chiếu mạnh tới chính đối tượng được theo dõi. Bài Cleaner cuối chương giải thích thiết kế trạng thái độc lập và các bẫy tham chiếu.

## 6. Rà soát mã cũ và kiểm tra khả năng tương thích

Khi bảo trì codebase có finalizer:

1. Tìm lớp ghi đè `finalize()`, cả ở source và các thư viện phụ thuộc. Kiểm tra tài nguyên nào thực sự được sở hữu, ai chịu trách nhiệm đóng và đường đi xử lý ngoại lệ.
2. Chuyển thao tác dọn dẹp chính sang `close()` hoặc API đóng tương đương; cập nhật nơi gọi bằng `try-with-resources` hoặc `finally` khi thích hợp.
3. Nếu cần lớp dự phòng cho native resource, cân nhắc `Cleaner` với state không tham chiếu tới chính đối tượng được đăng ký.
4. Kiểm thử đường đi bình thường, ngoại lệ, gọi `close()` lặp lại, và trường hợp đóng tài nguyên chưa từng dùng.
5. Thử chạy với finalization bị tắt để phát hiện phụ thuộc còn sót:

```bash
# Tùy chọn có từ JDK 18; thay App bằng main class thực tế.
java --finalization=disabled App
```

Có thể dùng `jdeprscan --for-removal your-app.jar` để tìm các tham chiếu API chuẩn đã đánh dấu for removal trong file JAR. Tuy nhiên việc quét bytecode **không thay cho việc tìm các phương thức `finalize()` do dự án tự khai báo**; cần kiểm tra source, thư viện và hành vi tài nguyên. Không dùng `System.runFinalization()` như biện pháp khắc phục: API này cũng deprecated for removal và không cung cấp sự bảo đảm dọn dẹp cần thiết.

## 7. Sai lầm phổ biến và cách ghi nhớ

- **Sai:** “GC thu hồi đối tượng thì mọi file/socket của nó được đóng đúng lúc.” **Đúng:** GC chủ yếu thu hồi bộ nhớ Java; tài nguyên ngoài heap cần vòng đời đóng riêng.
- **Sai:** “Dùng `finally` và `finalize()` là như nhau.” **Đúng:** `finally` thuộc luồng thực thi của mã; `finalize()` phụ thuộc cơ chế finalization.
- **Sai:** “`deprecated for removal` có nghĩa là `finalize()` đã bị xóa.” **Đúng:** Nó cảnh báo có kế hoạch loại bỏ trong tương lai; hãy kiểm tra API/JDK mục tiêu.
- **Sai:** “Đăng ký Cleaner là có thể bỏ `close()`.” **Đúng:** Cleaner chỉ phù hợp làm lớp bảo vệ dự phòng không bảo đảm thời điểm.
- **Sai:** “Chờ `System.gc()` cho tới khi finalizer chạy là test ổn định.” **Đúng:** Hãy test thao tác đóng chủ động và trạng thái tài nguyên quan sát được.

**Nguyên tắc thiết kế:** đối tượng nào sở hữu tài nguyên thì phải cung cấp cách đóng rõ ràng; mã sử dụng phải xác định được thời điểm đóng. `Object.finalize()` là cơ chế lịch sử cần loại khỏi thiết kế mới.

## 8. Tài liệu chính thức

- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)
- [Java SE 26 — API `java.lang.Object.finalize()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#finalize())
- [Java SE 26 — JLS §12.6, Finalization of Class Instances](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html#jls-12.6)
- [Java SE 26 — `Cleaner` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Java SE 26 — `AutoCloseable` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html)
