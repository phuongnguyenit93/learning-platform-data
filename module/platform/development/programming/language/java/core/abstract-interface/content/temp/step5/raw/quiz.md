Câu 1. Với khai báo `abstract class Device`, thao tác nào đúng khi sử dụng kiểu `Device`?
A. Có thể tạo `new Device()` nếu mọi method trong lớp có body.
B. Có thể khởi tạo `new Device()` khi constructor được khai báo public.
C. Có thể khai báo biến `Device d` nhưng không tạo `new Device()`.
D. Có thể dùng `new Device()` sau khi lớp được nạp vào JVM.
Đáp án đúng: C

Câu 2. Một abstract class trong Java có thể khai báo constructor để làm gì?
A. Constructor abstract được gọi trước khi class con tồn tại.
B. Constructor base chạy qua `super(...)` khi tạo object lớp con.
C. Constructor abstract biến method abstract thành default method.
D. Constructor abstract cho phép tạo instance trực tiếp bằng `new`.
Đáp án đúng: B

Câu 3. Trong `abstract class Report`, nhận định nào đúng về phương thức có phần thân?
A. Lớp abstract phải để mọi instance method ở dạng abstract.
B. Lớp abstract có cả method có body lẫn abstract method.
C. Lớp abstract chỉ được chứa static method có phần thân.
D. Lớp abstract không có method cụ thể được lớp con kế thừa.
Đáp án đúng: B

Câu 4. Một lớp `Invoice` extends abstract `Document` nhưng chưa hiện thực `print()` abstract; điều gì đúng?
A. Class dùng `print()` tự sinh, trả về null ở runtime.
B. Class được JVM sinh method `print()` rỗng khi load.
C. Class phải implement `print()` hoặc khai báo `abstract`.
D. Class luôn cụ thể khi đã extends một abstract superclass.
Đáp án đúng: C

Câu 5. Khai báo method abstract nào hợp lệ trong một abstract class?
A. Hợp lệ: `private abstract void draw();` trong class.
B. Hợp lệ: `protected abstract void draw();`.
C. Hợp lệ: `static abstract void draw();`.
D. Hợp lệ: `final abstract void draw();`.
Đáp án đúng: B

Câu 6. Một Java class thông thường muốn kế thừa hai abstract class độc lập thì sao?
A. Class có thể `extends A implements B` khi B là abstract class.
B. Class có thể `implements A, B` để dùng constructor của hai lớp.
C. Class có thể `extends A, B` nếu cả A và B đều abstract.
D. Class không được `extends` đồng thời hai superclass trực tiếp.
Đáp án đúng: D

Câu 7. Một abstract class implements `Runnable` nhưng không định nghĩa `run()` thì điều gì đúng?
A. Lớp abstract có thể để lớp con cụ thể thực hiện `run()`.
B. Lớp abstract phải implement `run()` trước khi có subclass.
C. Lớp con có thể bỏ `run()` nếu đã khai báo constructor.
D. Lớp được cung cấp `run()` từ lớp `Thread` mặc định.
Đáp án đúng: A

Câu 8. Với biến kiểu `Animal` và class con `Dog`, điều gì quyết định method nào được phép gọi trực tiếp qua biến?
A. Kiểu khai báo `Animal` quyết định tập member truy cập ở compile time.
B. Kiểu thực tế `Dog` làm mọi method riêng của Dog gọi được trực tiếp.
C. Tên object tại heap quyết định mọi method được trình biên dịch cho qua.
D. Class loader quyết định method mới được thêm vào biến tại runtime.
Đáp án đúng: A

Câu 9. Một class Java muốn thực hiện cả `Readable` lẫn `Closeable` là interface thì khai báo nào phù hợp?
A. Dùng `class FileTask extends Readable, Closeable`.
B. Dùng `interface FileTask implements Readable, Closeable`.
C. Dùng `class FileTask implements Readable extends Closeable`.
D. Dùng `class FileTask implements Readable, Closeable`.
Đáp án đúng: D

Câu 10. Một interface `Combined` muốn kế thừa hai interface `A` và `B`, cú pháp nào đúng?
A. Dùng `interface Combined extends A, B`.
B. Dùng `class Combined extends A, B` để kế thừa.
C. Dùng `interface Combined implements A, B`.
D. Dùng `interface Combined extends A implements B`.
Đáp án đúng: A

Câu 11. Trong Java, field khai báo `int LIMIT = 10;` bên trong interface có đặc tính nào?
A. Field là `private static` khi interface không ghi access modifier.
B. Field là `protected final` và được sửa trong constructor lớp con.
C. Field được xem là `public static final` dù không viết tường minh.
D. Field là biến instance có thể khác nhau giữa các object triển khai.
Đáp án đúng: C

Câu 12. Một interface khai báo `void send();` mà không có body hay modifier thì method có tính chất nào?
A. Method được ngầm định `public default` trong interface.
B. Method được ngầm định `private static` trong interface.
C. Method được ngầm định `public abstract` trong interface.
D. Method được ngầm định `protected abstract` trong interface.
Đáp án đúng: C

Câu 13. Khi class implement `interface Job { void run(); }`, method `run()` trong class phải có visibility nào?
A. Method `run()` được để protected vì interface thiếu modifier.
B. Method `run()` implement interface phải là `public`.
C. Method `run()` được để package-private nếu class cùng package.
D. Method `run()` được để private khi class dùng nội bộ.
Đáp án đúng: B

Câu 14. Lợi ích kỹ thuật của `@Override` khi hiện thực method interface là gì?
A. Annotation đổi method thành final ngay khi class được nạp.
B. Annotation cho phép giảm visibility khi override method.
C. Annotation cấp body mặc định khi method chưa được hiện thực.
D. `@Override` báo lỗi nếu method không thật sự override.
Đáp án đúng: D

Câu 15. Từ Java 8, cú pháp nào mô tả đúng một default method trong interface?
A. Dùng `default void ping() { ... }` để cung cấp phần thân.
B. Dùng `private default void ping() { ... }` để khai báo method.
C. Dùng `abstract default void ping();` để cung cấp phần thân.
D. Dùng `static default void ping() { ... }` để khai báo method.
Đáp án đúng: A

Câu 16. Một class implements `Notifier` có `default void notifyUser()`; class có thể làm gì?
A. Class override default method bằng method `final abstract`.
B. Class có thể override default method bằng method `public` của nó.
C. Class override default method bằng method `private` cùng tên.
D. Class override default method bằng method `static` cùng tên.
Đáp án đúng: B

Câu 17. Superclass đã có method instance `public void save()`, interface có default method cùng chữ ký; phương án nào thắng?
A. JVM buộc subclass override lại cả hai method vì không có ưu tiên.
B. Method cụ thể từ class hierarchy được ưu tiên hơn interface default.
C. Phương thức được gọi phụ thuộc thứ tự tên interface trong implements.
D. Default method interface luôn thay thế method class khi trùng tên.
Đáp án đúng: B

Câu 18. Class `C implements A, B`, trong đó A và B không liên quan đều có `default void f()`; xử lý nào cần thiết?
A. `C` override `f()` để giải quyết xung đột default method.
B. `C` nhận hai method cùng signature và chọn ngẫu nhiên khi gọi.
C. JVM chọn default method của A vì A đứng trước B.
D. JVM chọn default method theo thứ tự interface được nạp.
Đáp án đúng: A

Câu 19. `Child extends Parent` là interface và cả hai có default method `m()`; class implements Child thường nhận bản nào?
A. Default của Parent được ưu tiên vì Parent xuất hiện trước.
B. Class phải override m vì có hai interface cùng method.
C. Default của Child được chọn nhờ tính đặc hiệu trong hierarchy.
D. JVM chạy cả Parent.m lẫn Child.m khi gọi một lần.
Đáp án đúng: C

Câu 20. Interface `Utility` có `static int version()`, cách gọi hợp lệ từ bên ngoài là gì?
A. Gọi `Utility.version()` qua tên interface đã khai báo method.
B. Gọi `Utility.super.version()` trong class bất kỳ implements Utility.
C. Gọi `Impl.version()` khi Impl implements Utility và không khai báo.
D. Gọi `new Utility().version()` vì method static có sẵn.
Đáp án đúng: A

Câu 21. Một class `Impl implements Utility`, với Utility có static method `help()`; điều gì đúng?
A. Static method interface không được `Impl` kế thừa.
B. `Impl` kế thừa method và gọi qua `new Impl().help()`.
C. `Impl` override method bằng cách dùng annotation `@Override`.
D. Method của interface biến thành instance method trong Impl.
Đáp án đúng: A

Câu 22. Từ Java 9, private method trong interface hữu ích cho tình huống nào?
A. Thay thế constructor của interface để khởi tạo instance state.
B. Được gọi trực tiếp từ instance của class implement interface.
C. Trở thành method được class triển khai override bắt buộc.
D. Chia sẻ logic nội bộ giữa các default hoặc static method.
Đáp án đúng: D

Câu 23. Nếu interface khai báo `int count = 0`, class implement có thể tăng `count++` trực tiếp hay không?
A. Có, vì biến interface trở thành field instance của class.
B. Không, field trong interface là final nên không thể gán lại.
C. Có, vì từ Java 8 interface cho phép field thay đổi trạng thái.
D. Có, nếu class implement không khai báo method abstract.
Đáp án đúng: B

Câu 24. Hai interface độc lập đều khai báo `void execute();` abstract với cùng signature; class implement cả hai cần gì?
A. Một method `public execute()` có thể thỏa cả hai.
B. Không thể implement hai interface có cùng chữ ký abstract.
C. Cần hai method execute riêng phân biệt theo từng interface.
D. Chỉ cần method `protected execute()` cho cả hai interface.
Đáp án đúng: A

Câu 25. Với `Shape shape = new Circle();` và `draw()` được override, lệnh `shape.draw()` chọn logic nào?
A. Gọi constructor Shape để chọn implementation của draw.
B. Gọi bản `Shape.draw()` vì biến được khai báo kiểu Shape.
C. Gọi method theo tên class của file nguồn chứa lệnh gọi.
D. Dispatch gọi `Circle.draw()` theo object runtime.
Đáp án đúng: D

Câu 26. Khi nhiều implementation không chung cây class cần hợp đồng `PaymentProcessor`, nên ưu tiên cách nào?
A. Tạo các static method trong một enum rồi thay đa hình.
B. Định nghĩa một lớp final để các lớp khác extends trực tiếp.
C. Buộc mọi class extends một base class chỉ để khai báo chữ ký.
D. Tạo interface để các class độc lập cùng implement hợp đồng.
Đáp án đúng: D

Câu 27. Khi nhiều lớp con cần dùng trạng thái bảo vệ và constructor khởi tạo chung, lựa chọn nào thích hợp?
A. Dùng interface với instance field private và constructor.
B. Dùng interface với constructor và mutable instance field.
C. Dùng abstract class khi cần state và constructor chung.
D. Dùng final class với constructor cùng abstract method.
Đáp án đúng: C

Câu 28. Khi override method `Number result()` trong subclass, return type nào hợp lệ?
A. Return `Object` là covariant vì Object là supertype Number.
B. Return `String` là covariant vì cùng là reference type.
C. Return `int` là covariant vì int có thể được boxing thành Integer.
D. Return `Integer` là covariant vì Integer là subtype của Number.
Đáp án đúng: D

Câu 29. Superclass khai báo `void load() throws IOException`; subclass override có thể làm gì với checked exception?
A. Dùng `throws SQLException` vì đều là checked exception trong Java.
B. `throws FileNotFoundException` hợp lệ vì là subtype IOException.
C. `throws Throwable` hợp lệ vì bao phủ IOException.
D. `throws Exception` hợp lệ vì rộng hơn IOException.
Đáp án đúng: B

Câu 30. Superclass có `public final void lock()`; subclass muốn đổi hành vi `lock()` thì sao?
A. Abstract subclass vẫn có thể override final method.
B. Thêm `@Override` cho phép override final method.
C. `final` ngăn subclass override method `lock()`.
D. Đánh dấu synchronized cho phép override final method.
Đáp án đúng: C

Câu 31. Interface có một abstract method `convert()` cùng vài default/static method; điều gì đúng về lambda?
A. Lambda biến interface thành abstract class ở compile time.
B. Default/static method được tính nên interface không còn functional.
C. Chỉ interface có đúng một method tổng cộng mới nhận được lambda.
D. Interface vẫn là functional interface và có thể làm đích lambda.
Đáp án đúng: D

Câu 32. Tại sao gọi method có thể override từ constructor abstract class cần thận trọng?
A. Method luôn gọi bản superclass trước khi tạo object lớp con.
B. Field subclass được khởi tạo trước khi gọi super constructor.
C. Override có thể chạy trước khi field subclass khởi tạo.
D. JVM bỏ qua override cho tới khi constructor kết thúc.
Đáp án đúng: C
