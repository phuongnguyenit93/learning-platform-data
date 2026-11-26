Câu 01. Annotation trong Java được dùng chủ yếu để biểu diễn điều gì?
A. Một dạng statement bắt JVM gọi method khi gặp dấu `@`
B. Một bản cấu hình tự thực thi trước constructor của object
C. Cơ chế thay thế cấu trúc interface và generic type của Java
D. Metadata gắn với code để compiler, công cụ hoặc runtime phân tích
Đáp án đúng: D

Câu 02. Cú pháp nào khai báo một annotation type tên `Audit` hợp lệ trong Java?
A. `public class Audit extends @interface { }` khai báo type
B. `public interface @Audit { }` khai báo annotation type
C. `public annotation Audit { }` khai báo annotation type
D. Khai báo `public @interface Audit { }` là annotation type hợp lệ
Đáp án đúng: D

Câu 03. Một marker annotation thường có đặc điểm nào?
A. Không khai báo element, ví dụ `@interface Marker {}`
B. Có một method abstract `boolean enabled()` cần truyền
C. Chứa ít nhất một field instance để ghi metadata
D. Phải có element tên `value` với giá trị mặc định
Đáp án đúng: A

Câu 04. Trong thân `@interface Label`, cách khai báo element trả `String` tên `value` là gì?
A. `String value(String x);` là element có tham số
B. `void value(String x);` khai báo element không có tham số
C. Dùng `String value();` để khai báo element mong muốn
D. `String value;` là khai báo element annotation
Đáp án đúng: C

Câu 05. Kiểu trả về nào hợp lệ cho một element của annotation type?
A. `Map<String,String>` là kiểu metadata được phép khai báo
B. `List<String>` là kiểu metadata được phép khai báo
C. `Optional<String>` là kiểu metadata được phép khai báo
D. `Class<?>` có thể dùng làm kiểu element của annotation
Đáp án đúng: D

Câu 06. Kiểu nào không hợp lệ làm return type của annotation element?
A. `String[]` không thuộc tập kiểu element được Java chấp nhận
B. `int` không thuộc tập kiểu element được Java chấp nhận
C. `RetentionPolicy` không thuộc tập kiểu element được chấp nhận
D. `List<String>` là loại kiểu không dùng cho annotation element
Đáp án đúng: D

Câu 07. Trong annotation type, từ khóa nào khai báo giá trị mặc định cho element?
A. `fallback` đặt giá trị nếu nơi sử dụng không khai báo element
B. `optional` đặt giá trị nếu nơi sử dụng không khai báo element
C. `default` đặt giá trị nếu nơi sử dụng không khai báo element
D. `initial` đặt giá trị nếu nơi sử dụng không khai báo element
Đáp án đúng: C

Câu 08. Nếu annotation element không có default mà nơi dùng bỏ qua element đó, điều gì xảy ra?
A. Reflection tự thêm một default mới khi đọc annotation
B. JVM tự gán `null` vào element khi tạo annotation instance
C. Compiler báo lỗi vì giá trị element chưa được cung cấp
D. Compiler tự dùng zero value tương ứng với kiểu element
Đáp án đúng: C

Câu 09. Với `@interface Note { String value(); }`, cú pháp dùng nào là hợp lệ?
A. `@Note(value("ready"))` dùng shorthand cho element `value`
B. `@Note("value" = "ready")` gán element theo tên
C. `@Note(value -> "ready")` dùng lambda cho value
D. `@Note("ready")` dùng shorthand cho element `value`
Đáp án đúng: D

Câu 10. Với element `String[] tags()`, cách gán một phần tử khi sử dụng annotation là gì?
A. `@Tags(tags = "api")` dùng dạng rút gọn của mảng một phần tử
B. `@Tags(tags = List.of("api"))` dùng factory của List
C. `@Tags(tags = String.valueOf("api"))` gọi Java method
D. `@Tags(tags = new String[]{"api"})` cần tạo array bằng new
Đáp án đúng: A

Câu 11. Khai báo nào không hợp lệ cho element trong một annotation type?
A. `RetentionPolicy value();` dùng hằng enum làm annotation
B. `String[] values();` dùng mảng một chiều các String
C. `String[][] values();` là dạng mảng nhiều chiều bị cấm
D. `Class<?> value();` dùng class literal làm annotation value
Đáp án đúng: C

Câu 12. `@Target(ElementType.METHOD)` giới hạn annotation ở vị trí nào?
A. Lời khai báo field, không áp dụng cho method declaration
B. Biểu thức gọi method, không áp dụng lên method declaration
C. Tham số type của generic method, không lên method declaration
D. Lời khai báo method, không áp dụng cho field declaration
Đáp án đúng: D

Câu 13. Để annotation đặt ở vị trí type use như `List<@Safe String>`, chọn Target nào?
A. `ElementType.TYPE_USE` dùng cho annotation tại type use
B. `ElementType.PARAMETER` cho phép ghi vào type argument
C. `ElementType.FIELD` cho phép đặt trên generic type use
D. `ElementType.TYPE` cho phép ghi annotation ở type use
Đáp án đúng: A

Câu 14. Để annotate biến kiểu generic `T` trong `class Box<@Marker T>`, Target nào đúng?
A. `ElementType.TYPE_PARAMETER` áp dụng vào khai báo tham số kiểu
B. `ElementType.CONSTRUCTOR` áp dụng lên type parameter
C. `ElementType.TYPE` áp dụng lên type parameter declaration
D. `ElementType.LOCAL_VARIABLE` áp dụng lên type parameter
Đáp án đúng: A

Câu 15. Muốn giới hạn annotation vào chính declaration của record component, dùng Target nào?
A. `ElementType.FIELD` chỉ định record component declaration
B. `ElementType.METHOD` chỉ định record component declaration
C. `ElementType.RECORD_COMPONENT` áp dụng cho khai báo record component
D. `ElementType.PARAMETER` chỉ định record component declaration
Đáp án đúng: C

Câu 16. Khi đặt `@Retention(RetentionPolicy.SOURCE)`, annotation còn lại ở đâu?
A. Có trong `.class` nhưng không đọc được bằng reflection
B. Không được compiler nhận diện ngay trong source code
C. Có trong `.class` và đọc được bằng runtime reflection
D. Có ở source nhưng không lưu vào output `.class` của compiler
Đáp án đúng: D

Câu 17. `RetentionPolicy.CLASS` có ý nghĩa nào với annotation?
A. Chỉ lưu vào tài liệu Javadoc mà không ghi class file
B. Lưu trong `.class` nhưng không hiển thị qua runtime reflection
C. Bị compiler loại khỏi class file như retention SOURCE
D. Được runtime reflection đọc như retention RUNTIME
Đáp án đúng: B

Câu 18. Để đọc annotation bằng `getAnnotation` tại runtime, retention nào cần dùng?
A. `RetentionPolicy.RUNTIME` cho phép phản chiếu lúc chạy
B. `RetentionPolicy.CLASS` giữ metadata cho runtime reflection
C. `RetentionPolicy.SOURCE` giữ metadata cho runtime reflection
D. `RetentionPolicy.METHOD` giữ metadata cho runtime reflection
Đáp án đúng: A

Câu 19. Nếu annotation type không khai báo `@Retention`, chính sách mặc định là gì?
A. `RetentionPolicy.SOURCE` bỏ annotation khi compile
B. `RetentionPolicy.INHERITED` giữ annotation khi kế thừa
C. `RetentionPolicy.CLASS` giữ annotation vào class file
D. `RetentionPolicy.RUNTIME` giữ annotation đọc qua reflection
Đáp án đúng: C

Câu 20. Tác dụng của meta-annotation `@Inherited` trong Java là gì?
A. Cho phép field con kế thừa annotation của field bị shadow
B. Cho phép method override tự nhận annotation trên method gốc
C. Subclass có thể thừa hưởng class annotation từ superclass
D. Cho phép class nhận annotation từ các interface implemented
Đáp án đúng: C

Câu 21. Với annotation được đánh dấu `@Inherited`, điều nào đúng khi class implement một interface có annotation đó?
A. Class không thừa hưởng annotation gắn trên interface đã implement
B. Annotation trên interface thành annotation declared của class cài đặt
C. Annotation trên interface được sao chép vào các method implementation
D. Annotation trên interface tạo record component metadata của class
Đáp án đúng: A

Câu 22. Muốn gắn cùng annotation `@Tag` nhiều lần vào một element, type `Tag` cần gì?
A. `@Target(Tags.class)` khai báo container annotation phù hợp
B. Dùng `@Repeatable(Tags.class)` với container thích hợp
C. `@Documented(Tags.class)` khai báo container annotation phù hợp
D. `@Inherited(Tags.class)` khai báo container annotation phù hợp
Đáp án đúng: B

Câu 23. Container annotation `Tags` cho repeatable annotation `Tag` cần khai báo gì?
A. Element `List<Tag> value();` để chứa các lần lặp của `Tag`
B. Element `Tag[] value();` chứa các lần lặp dưới dạng mảng Tag
C. Element `String[] names();` để chứa các lần lặp của `Tag`
D. Element `Class<Tag> value();` để chứa các lần lặp của `Tag`
Đáp án đúng: B

Câu 24. Để lấy các `@Tag` lặp lại trên cùng một class thông qua reflection, API nào phù hợp?
A. `getAnnotation(Tag.class)` trả danh sách các `Tag` lặp lại
B. `getDeclaredMethods()` trả các `Tag` lặp lại trên class
C. `getParameterAnnotations()` trả các `Tag` trên class
D. `getAnnotationsByType(Tag.class)` lấy các Tag lặp lại
Đáp án đúng: D

Câu 25. `@Documented` trên một annotation type ảnh hưởng chính đến công cụ nào?
A. JVM mở quyền private reflection để đọc annotation
B. ServiceLoader đăng ký provider cho annotation type
C. Javac buộc processor sinh source file từ annotation
D. Javadoc đưa annotation vào tài liệu API được sinh
Đáp án đúng: D

Câu 26. Ý nghĩa của `@Deprecated(forRemoval = true)` đối với một API là gì?
A. Đánh dấu API chỉ dùng được khi bật Java preview flags
B. Đánh dấu API deprecated có ý định loại bỏ trong tương lai
C. Đánh dấu API để compiler xóa method khỏi bytecode build
D. Đánh dấu API thành private kể từ lần compile tiếp theo
Đáp án đúng: B

Câu 27. Khi dùng `@Override` trên method không thực sự override hoặc implement method hợp lệ, điều gì xảy ra?
A. Compiler tự tìm method cùng tên rồi sửa tham số cho khớp
B. Runtime ném lỗi khi method bị invoke lần đầu tiên
C. Compiler báo lỗi vì method không có override hợp lệ
D. Javadoc loại method này khỏi trang API của class
Đáp án đúng: C

Câu 28. `@SuppressWarnings("unchecked")` giải quyết vấn đề theo cách nào?
A. Đảm bảo phép ép kiểu generic được kiểm tra sâu lúc chạy
B. Bắt compiler bỏ phần bytecode có thao tác unchecked
C. Compiler giảm warning unchecked trong phạm vi annotate
D. Chặn runtime ClassCastException từ các generic casts
Đáp án đúng: C

Câu 29. Để lấy annotation runtime trực tiếp khai báo trên class, không tính inherited, gọi gì?
A. `getDeclaredAnnotation(Audit.class)` bỏ qua annotation inherited
B. `getMethod(Audit.class)` chỉ tìm khai báo trực tiếp
C. `getAnnotation(Audit.class)` chỉ tìm khai báo trực tiếp
D. `getAnnotationsByType(Audit.class)` chỉ tìm khai báo trực tiếp
Đáp án đúng: A

Câu 30. Để đọc annotation `TYPE_USE` trên type của một field, API reflection nào phù hợp?
A. `Field.getDeclaringClass()` cho annotation trên type của field
B. `Field.getAnnotatedType()` cho thông tin annotation trên type
C. `Field.getGenericType()` trả `AnnotatedType` trực tiếp
D. `Field.getAnnotations()` trả annotation trên generic type use
Đáp án đúng: B

Câu 31. Muốn đọc annotation đặt trên từng parameter declaration của method, API nào phù hợp?
A. `Method.getTypeParameters()` trả annotations của tham số thực
B. `Method.getParameterAnnotations()` đọc theo từng tham số
C. `Method.getExceptionTypes()` trả annotations theo tham số
D. `Method.getAnnotatedReturnType()` trả annotations theo tham số
Đáp án đúng: B

Câu 32. API chuẩn để tự viết annotation processor của javac nằm trong package nào?
A. `javax.annotation.processing` chứa Processor và AbstractProcessor của JDK
B. `java.lang.reflect.processing` chứa Processor và AbstractProcessor
C. `jakarta.annotation.processing` chứa Processor và AbstractProcessor
D. `java.lang.annotation.processing` chứa Processor và AbstractProcessor
Đáp án đúng: A

Câu 33. Lớp nền tiện ích nào của Java thường được kế thừa khi xây annotation processor?
A. `Annotation` triển khai các phần nền của Processor API
B. `AbstractProcessor` cung cấp bộ khung của Processor API
C. `RoundEnvironment` triển khai các phần nền của Processor API
D. `Elements` triển khai các phần nền của Processor API
Đáp án đúng: B

Câu 34. `@SupportedAnnotationTypes` trên processor dùng để khai báo thông tin nào?
A. Tập Java source versions mà processor có thể biên dịch
B. Các annotation types được processor khai báo hỗ trợ xử lý
C. Những class loader có thể nạp annotation trên module path
D. Những kiểu Java mà processor được phép tạo instance
Đáp án đúng: B

Câu 35. Mục đích của `@SupportedSourceVersion` trên processor là gì?
A. Khai báo source retention của annotation đang được quét
B. Khai báo version của dependency runtime cho JAR provider
C. Khai báo version serialization của annotation proxy
D. Mức phiên bản source Java mà processor hỗ trợ xử lý
Đáp án đúng: D

Câu 36. Trong `process(...)`, API nào lấy các element có annotation `@Check` ở round hiện tại?
A. `processingEnv.getFiler().getElementsAnnotatedWith(Check.class)`
B. `processingEnv.getMessager().getElementsAnnotatedWith(Check.class)`
C. `roundEnv.getElementsAnnotatedWith(Check.class)` tra elements
D. `roundEnv.getRootElements(Check.class)` chọn theo annotation
Đáp án đúng: C

Câu 37. Annotation processor muốn báo lỗi compile tại một element nên dùng API nào?
A. `RoundEnvironment.printMessage(Diagnostic.Kind.ERROR, ...)`
B. `Messager.printMessage(Diagnostic.Kind.ERROR, ..., element)`
C. `Elements.getTypeElement(Diagnostic.Kind.ERROR, element)`
D. `Filer.createSourceFile(Diagnostic.Kind.ERROR, ..., element)`
Đáp án đúng: B

Câu 38. API nào cho phép annotation processor tạo file Java source mới theo quy tắc Filer?
A. `processingEnv.getElementUtils().createSourceFile(name)` tạo nguồn
B. `processingEnv.getFiler().createSourceFile(name)` tạo nguồn mới
C. `processingEnv.getMessager().createSourceFile(name)` tạo nguồn mới
D. `roundEnv.createSourceFile(name)` tạo file trong round tiếp
Đáp án đúng: B

Câu 39. Một processor sinh Java source mới trong round hiện tại thì javac có thể làm gì tiếp?
A. Tiếp tục vòng processing mới để xem xét source vừa sinh
B. Dừng processing ngay khi file được Filer đóng lần đầu
C. Xem source sinh ra là bytecode đã biên dịch hoàn chỉnh
D. Nạp class sinh ra vào JVM của ứng dụng trước khi compile
Đáp án đúng: A

Câu 40. Với `javac -proc:only`, kết quả công việc biên dịch được giới hạn thế nào?
A. Chạy annotation processors mà không biên dịch class từ source
B. Chỉ lưu annotation RUNTIME và loại bỏ các annotation CLASS
C. Chỉ chạy tests với processor đã đăng ký trên module path
D. Biên dịch class nhưng vô hiệu hóa các annotation processors
Đáp án đúng: A
