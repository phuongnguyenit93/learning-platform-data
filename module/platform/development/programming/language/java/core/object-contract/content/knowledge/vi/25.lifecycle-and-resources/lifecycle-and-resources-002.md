# Không bảo đảm thời điểm hoặc việc finalizer sẽ được chạy

## 1. Vấn đề cốt lõi

Trong Java, **finalizer** là phương thức `finalize()` mà một lớp có thể ghi đè để yêu cầu thực hiện một thao tác khi đối tượng chuẩn bị được bộ thu gom rác (Garbage Collector, GC) xử lý. Đây là cơ chế dọn dẹp cũ và **không đáng tin cậy để quản lý tài nguyên**.

Không có cam kết rằng:
- Một đối tượng sẽ được GC xử lý ngay khi nó không còn được chương trình sử dụng.
- `finalize()` sẽ được gọi trong một khoảng thời gian xác định, ngay cả khi đối tượng không còn được tham chiếu.
- `finalize()` của tất cả các đối tượng sẽ chạy trước khi ứng dụng kết thúc.
- Một finalizer thực thi thành công hoặc kịp giải phóng tài nguyên khi ứng dụng thiếu bộ nhớ, bị dừng hoặc JVM thoát.

**Hệ quả:** không dùng finalizer để đóng file, socket, kết nối cơ sở dữ liệu, giải phóng khóa, hoàn thành giao dịch, ghi dữ liệu quan trọng hoặc thực hiện bất kỳ hành động nào cần được bảo đảm về thời điểm.

Trong ngữ cảnh *vòng đời và tài nguyên*, cần tách rõ hai loại công việc:
- **Thu hồi bộ nhớ heap do JVM quản lý:** GC đảm nhiệm; chương trình không cần và không thể buộc thời điểm thu gom từng đối tượng.
- **Giải phóng tài nguyên có vòng đời nghiệp vụ hoặc tài nguyên bên ngoài heap:** ứng dụng phải quản lý tường minh, thường qua `AutoCloseable` và `try-with-resources`.

## 2. Finalization hoạt động thế nào và vì sao khó dự đoán?

Một mô hình đơn giản hóa:

~~~text
Tạo đối tượng
      |
      v
Đang có thể truy cập (reachable)
      |
      v
Không còn reachable theo quy tắc của JVM
      |
      v
Đủ điều kiện để GC xem xét
      |
      +---- GC chưa thực hiện / chưa xử lý đối tượng ----> chờ không xác định
      |
      v
Có thể được đưa vào xử lý finalization (cơ chế cũ)
      |
      +---- finalizer có thể bị trì hoãn, không hoàn tất
      |
      v
GC có thể thu hồi bộ nhớ khi điều kiện phù hợp
~~~

Sơ đồ này chỉ minh họa các quan hệ quan trọng; nó không phải một lịch trình mà JVM cam kết thực hiện theo từng bước tại một thời điểm nhất định.

### 2.1. Không còn tham chiếu không đồng nghĩa sẽ GC ngay

Khi chương trình không còn sử dụng đối tượng, bộ nhớ của nó **có thể** được thu gom. JVM quyết định thời điểm thu gom dựa trên hoạt động cấp phát, heap, thuật toán collector và những điều kiện khác. JVM có thể không chạy GC trước khi chương trình hoàn tất. Vì vậy, “đối tượng không còn dùng” không phải sự kiện để dự đoán thời điểm `finalize()`.

### 2.2. GC không đồng nghĩa finalizer sẽ hoàn tất

Ngay cả trong môi trường còn hỗ trợ finalization, việc một đối tượng trở nên đủ điều kiện xử lý không phải cam kết rằng finalizer của nó sẽ chạy trước một mốc thời gian cụ thể. Finalizer do cơ chế runtime thực hiện, không do luồng nghiệp vụ gọi tại nơi tài nguyên hết hạn sử dụng. Finalizer chậm, treo hoặc chờ khóa có thể cản trở quá trình dọn dẹp.

Các phiên bản Java mới đã đánh dấu finalization là cơ chế cần loại bỏ. `Object.finalize()` bị đánh dấu deprecated từ Java 9; Java 18 tiếp tục đánh dấu **deprecated for removal** theo JEP 421. Vì vậy, không nên thiết kế mã mới dựa vào phương thức này.

### 2.3. Gợi ý GC không phải lời hứa

~~~java
System.gc(); // Chỉ là yêu cầu/gợi ý GC; không bảo đảm finalizer được gọi
~~~

Lời gọi trên là một dòng Java minh họa, không phải chương trình độc lập. Nó không bảo đảm GC chạy, không bảo đảm đối tượng cụ thể được xử lý, và **không bảo đảm thời điểm hay sự thực thi của `finalize()`**. Đặt `System.gc()` sau khi mất tham chiếu không biến finalizer thành cơ chế đóng tài nguyên an toàn.

### 2.4. Ứng dụng có thể kết thúc trước khi dọn dẹp

Khi một chương trình ngắn kết thúc, JVM không có nghĩa vụ chạy mọi finalizer đang chờ. Các tình huống dừng bất thường càng khiến việc dựa vào finalizer rủi ro hơn. Một tài nguyên như file descriptor hoặc socket vì thế có thể không được giải phóng **đúng lúc** chỉ nhờ chờ GC.

Hệ điều hành thường thu hồi nhiều tài nguyên khi tiến trình kết thúc, nhưng điều đó không thay thế việc ứng dụng đóng tài nguyên đúng vòng đời, flush nội dung cần thiết hay hoàn tất giao dịch.

## 3. Đặt finalizer đúng chỗ trong mô hình vòng đời

`finalize()` thuộc cơ chế xử lý reachability của GC; `finally` là cấu trúc điều khiển chạy khi rời `try` theo quy tắc Java; còn `final` ngăn một số thao tác gán, override hoặc kế thừa. Vì vậy, một biến `final` hoặc một khối `finally` không làm finalizer có khả năng chạy đúng hạn. Bài phân biệt ba từ khóa ở phần sau làm rõ cú pháp và các trường hợp `return`/`throw`.

## 4. Thực hành đối chiếu: đóng ngay hay chờ GC?

Đối với tài nguyên mà chính đoạn mã sở hữu, đặt thao tác sử dụng trong `try-with-resources`:

~~~java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    System.out.println(in.read());
}
~~~

Đoạn ví dụ giả định `path` kiểu `Path` và mã gọi xử lý hoặc khai báo `IOException`. Khi ra khỏi khối, JVM thực hiện đường gọi `close()` theo ngôn ngữ Java; khi chỉ bỏ tham chiếu để chờ `finalize()`, chương trình không thể suy ra thời điểm giải phóng. `close()` vẫn có thể ném ngoại lệ, do đó người gọi phải xử lý lỗi thay vì coi cleanup luôn thành công. Chi tiết thứ tự đóng và suppressed exception được triển khai ở bài về `AutoCloseable`.

## 5. Tại sao dùng finalizer để đóng tài nguyên là sai?

Xét ý tưởng sai sau (chỉ minh họa, **không nên áp dụng**):

~~~java
// Mã minh họa bên trong một lớp nắm giữ tài nguyên, không phải chương trình hoàn chỉnh.
@Override
protected void finalize() throws Throwable {
    try {
        releaseNativeResource(); // Mong rằng GC sẽ gọi vào thời điểm thích hợp
    } finally {
        super.finalize();
    }
}
~~~

`releaseNativeResource()` là tên phương thức giả định để minh họa ý tưởng, không phải API có sẵn hay đoạn mã độc lập. Ngay cả khi phương thức cleanup đúng, chương trình vẫn có thể giữ file descriptor/socket/native memory cho đến một thời điểm không dự đoán được, thậm chí không gọi finalizer trước khi dừng.

Finalization còn tạo những vấn đề bổ sung:

- **Tồn đọng tài nguyên:** lượng bộ nhớ heap còn dư không phản ánh đầy đủ áp lực của file descriptor, kết nối mạng hoặc native memory; JVM có thể không thấy lý do cần GC ngay.
- **Hiệu năng:** đối tượng có finalizer có thể đòi hỏi xử lý GC phức tạp hơn; một finalizer chậm có thể làm chậm cleanup của đối tượng khác.
- **Không có thứ tự được bảo đảm:** không thể giả định finalizer của tài nguyên A chạy trước B dù A phụ thuộc B.
- **Ngoại lệ và thất bại:** ngoại lệ chưa được bắt trong finalizer không cung cấp cơ chế báo lỗi nghiệp vụ đáng tin cậy cho luồng đã sử dụng tài nguyên.
- **Object resurrection:** finalizer có thể làm đối tượng trở nên reachable lần nữa bằng cách lưu `this` ở nơi khác. Điều này khiến vòng đời khó suy luận; finalizer của cùng đối tượng không được JVM tự gọi lặp vô hạn chỉ vì nó lại trở nên unreachable.
- **An toàn và bảo trì:** finalizer thực thi ngoài luồng nghiệp vụ thông thường, khó xác định thứ tự, trạng thái và tương tác với cơ chế đồng bộ.

Nếu một tài nguyên phải được giải phóng ngay sau khi thao tác kết thúc, việc giải phóng phải là một phần của luồng xử lý hoặc vòng đời component được quản lý rõ ràng.

## 6. Cleaner không tạo ra hạn chót cho cleanup

`Cleaner` có thể dọn dẹp dự phòng sau khi một referent trở thành phantom-reachable, nhưng không có cam kết GC nhận diện nó và action hoàn tất trước một mốc thời gian. Khi cần đóng có tính xác định, cho owner gọi `close()`; một thư viện native có thể bổ sung `Cleaner` làm tuyến dự phòng. Nếu `close()` gọi `Cleanable.clean()`, đường chủ động thực hiện hành động ngay trong lời gọi; điều này khác với chờ Cleaner chạy tự động. Action không được giữ mạnh tham chiếu tới referent.

## 7. Những lỗi suy luận thường gặp

| Nhận định | Đánh giá chính xác |
| --- | --- |
| “Hết scope nghĩa là finalizer chạy ngay.” | Sai. Scope và reachability không xác lập lịch finalization. |
| “Đặt `System.gc()` trước khi thoát là đủ.” | Sai. Đây không phải cam kết GC/finalization. |
| “Finalizer sẽ đóng mọi file trước khi JVM kết thúc.” | Sai. Không được bảo đảm. |
| “`finally` chính là `finalize()`.” | Sai. `finally` gắn với luồng điều khiển; `finalize()` gắn với cơ chế GC cũ. |
| “`final` giúp một đối tượng tự giải phóng tài nguyên.” | Sai. `final` không quản lý vòng đời tài nguyên. |
| “Cleaner luôn chạy khi đối tượng không còn được dùng.” | Sai. Automatic cleaning không có hạn định hoặc bảo đảm trước shutdown. |
| “GC đã quản lý memory nên không cần đóng socket/stream.” | Sai. Tài nguyên hệ điều hành và hợp đồng flush/close cần xử lý riêng. |
| “`try-with-resources` gọi `close()` ngay khi rời khối.” | Đúng trong luồng thực thi Java bình thường, gồm cả khi phần thân ném ngoại lệ. |

## 8. Cách thiết kế vòng đời tài nguyên

Khi viết hoặc review một lớp Java sở hữu tài nguyên, hãy lần lượt xác định:

1. **Tài nguyên nào cần đóng?** Ví dụ file stream, socket, JDBC resource, native handle, executor hoặc một client có API `close()`/`shutdown()`.
2. **Ai sở hữu tài nguyên?** Quyền sở hữu quyết định ai có trách nhiệm đóng và lúc nào. Nếu phương thức tự mở resource dùng ngắn hạn, thường đóng ngay trong phương thức.
3. **Ranh giới vòng đời ở đâu?** Bao tài nguyên trong `try-with-resources` nếu phù hợp; với component dài hạn, bố trí lifecycle hook hoặc lời gọi `close()` tường minh từ component chủ quản.
4. **Nếu thao tác ném ngoại lệ thì sao?** Dùng `try-with-resources` hoặc `finally` đúng cách; quyết định cách log/xử lý ngoại lệ đóng và suppressed exceptions.
5. **Nếu người gọi quên đóng?** Có thể cân nhắc Cleaner làm cơ chế dự phòng cuối cùng cho một số native resources, nhưng vẫn coi quên đóng là lỗi hợp đồng.
6. **Kiểm tra bằng cách nào?** Test rằng `close()` được gọi đúng lần và đúng thời điểm, kể cả khi thao tác thất bại. Không viết test dựa vào `System.gc()` hoặc giấc ngủ cố định rồi mong `finalize()` xuất hiện.

Ví dụ câu hỏi kiểm tra kiến thức: “Một đối tượng mở file nhưng không còn tham chiếu. Có chắc file được đóng trong vòng một giây không?” **Không.** Việc đối tượng có thể bị thu gom không tạo cam kết về thời điểm GC hoặc finalizer. Nếu chương trình cần đóng file khi đọc xong, hãy dùng `try (InputStream in = ...) { ... }` và để `close()` xảy ra ở cuối khối.

## 9. Ghi nhớ

- **Finalization là cơ chế cũ, không dự đoán được và đã deprecated for removal.**
- **Không thể suy ra thời điểm chạy hay bảo đảm chạy finalizer từ việc mất tham chiếu, GC hoặc `System.gc()`.**
- **Hãy dọn tài nguyên theo quyền sở hữu và vòng đời rõ ràng:** `AutoCloseable`, `try-with-resources`, hoặc `close()`/`shutdown()` tại lúc kết thúc component.
- **Cleaner chỉ là lớp dự phòng cho một số trường hợp**, không thay thế cleanup tường minh.
