Câu 1. `obj.getClass()` trả về thông tin nào khi `obj` tham chiếu một lớp con?
A. Kiểu khai báo của biến đang giữ tham chiếu
B. Lớp thực tế mà đối tượng đang thuộc về
C. Lớp cha trực tiếp trong phân cấp kế thừa
D. Giao diện đầu tiên mà đối tượng triển khai
Đáp án đúng: B

Câu 2. Với `Class.forName("app.Widget")`, điều gì xảy ra khi tên lớp hợp lệ?
A. Nạp lớp nhưng luôn trì hoãn khởi tạo tĩnh
B. Tạo đối tượng qua constructor mặc định của lớp
C. Nạp và khởi tạo lớp nếu lớp chưa khởi tạo
D. Chỉ tìm tên lớp trong mã nguồn, không nạp lớp
Đáp án đúng: C

Câu 3. Biểu thức `Widget.class` cung cấp kết quả nào?
A. Đối tượng `Class` đại diện cho kiểu `Widget`
B. Tạo instance `Widget` qua constructor mặc định
C. Tìm kiểu runtime của một biến chưa được gán
D. Tạo ClassLoader mới rồi tải lại lớp `Widget`
Đáp án đúng: A

Câu 4. `getDeclaredFields()` trả về những field nào của lớp đang xét?
A. Chỉ field static trong lớp và các lớp cha
B. Chỉ field public, bỏ qua tất cả field private
C. Chỉ field public được kế thừa từ các lớp cha
D. Field khai báo trong lớp, kể cả field private
Đáp án đúng: D

Câu 5. Khác biệt chính của `getFields()` so với `getDeclaredFields()` là gì?
A. Chỉ lấy field public tự khai báo trong lớp
B. Chỉ lấy field có annotation lưu đến runtime
C. Field public của lớp, kể cả field kế thừa
D. Lấy mọi field trực tiếp, kể cả field private
Đáp án đúng: C

Câu 6. `getDeclaredMethods()` bao gồm những method nào?
A. Chỉ method instance, bỏ các method static
B. Method do lớp khai báo, kể cả method non-public
C. Chỉ method override từ interface mà lớp triển khai
D. Method public của lớp và tất cả lớp cha
Đáp án đúng: B

Câu 7. Khi gọi `clazz.getMethods()`, tập kết quả chứa gì?
A. Chỉ method có annotation runtime trên lớp
B. Tất cả method private và public của lớp
C. Chỉ method public do lớp khai báo trực tiếp
D. Method public của lớp, gồm cả method kế thừa
Đáp án đúng: D

Câu 8. `getDeclaredConstructor(String.class)` tìm constructor nào?
A. Constructor tự sinh nếu lớp thiếu kiểu `String`
B. Constructor ở các lớp cha có tham số `String`
C. Constructor của lớp nhận một tham số `String`
D. Constructor không tham số của lớp đang xét
Đáp án đúng: C

Câu 9. Về `getConstructor(...)` của `Class`, phát biểu nào đúng?
A. Luôn chọn constructor không tham số của lớp
B. Chỉ tìm constructor public theo chữ ký
C. Tìm cả constructor private của lớp theo chữ ký
D. Tìm constructor kế thừa từ các lớp cha
Đáp án đúng: B

Câu 10. `Modifier.isStatic(field.getModifiers())` kiểm tra điều gì?
A. Field có khai báo modifier `static` hay không
B. Giá trị hiện tại của field có khác `null` không
C. Field nằm trong lớp lồng nhau `static` hay không
D. Field có được truy cập từ package khác không
Đáp án đúng: A

Câu 11. Giả sử `B extends A`, kết quả `A.class.isAssignableFrom(B.class)` là gì?
A. Là `true` vì B có thể gán vào biến kiểu A
B. Là `false` vì chỉ xét hai lớp giống hệt nhau
C. Là `false` vì B là lớp con, không là lớp cha
D. Là `true` chỉ nếu A và B cùng một package
Đáp án đúng: A

Câu 12. `clazz.isInstance(value)` kiểm tra điều gì với `value` khác `null`?
A. Tên của biến có trùng tên lớp `clazz` không
B. Giá trị có tương thích kiểu `clazz` tại runtime
C. Object có được tạo từ constructor public không
D. Object có field trùng với các field của `clazz` không
Đáp án đúng: B

Câu 13. `String[].class.getComponentType()` trả về đối tượng nào?
A. Trả `Object.class`, vì mảng cũng là object
B. Trả `String.class`, kiểu phần tử của mảng
C. Trả `null`, vì mảng không có kiểu phần tử
D. Trả `String[].class`, kiểu của cả mảng
Đáp án đúng: B

Câu 14. Khi đọc một `int` field bằng `Field.get(obj)`, kết quả thuộc dạng nào?
A. Giá trị `int` được boxing thành `Integer`
B. Giá trị field luôn thành chuỗi biểu diễn của số
C. Giá trị field luôn thành `Optional<Integer>`
D. Giá trị primitive luôn giữ nguyên, không boxing
Đáp án đúng: A

Câu 15. Tham số đối tượng đích của `Field.get` dùng thế nào với field static?
A. Chỉ truyền `null` khi field static là private
B. Truyền `null` luôn ném `NullPointerException`
C. Có thể truyền `null` khi đọc giá trị field static
D. Phải truyền instance dù field được khai báo static
Đáp án đúng: C

Câu 16. Khi gọi `Method.invoke` cho method static, target truyền vào có thể là gì?
A. Không thể gọi method static bằng Reflection API
B. Có thể dùng `null` để gọi method static
C. Luôn phải truyền instance dù method là static
D. Phải truyền một đối tượng `Class` thay cho `null`
Đáp án đúng: B

Câu 17. Nếu method được gọi qua `Method.invoke` tự ném ngoại lệ, Reflection phản hồi thế nào?
A. Reflection ném trực tiếp cùng đối tượng lỗi gốc
B. Lỗi được bọc trong `InvocationTargetException`
C. Lỗi luôn bị đổi thành `IllegalAccessException`
D. Reflection nuốt lỗi rồi trả về giá trị `null`
Đáp án đúng: B

Câu 18. Từ `InvocationTargetException`, làm sao lấy được ngoại lệ do method đích ném?
A. Dùng `getCause()` để lấy ngoại lệ gốc
B. Gọi `getSuppressed()` để lấy đúng đối tượng gốc
C. Gọi `getMessage()` để lấy đúng đối tượng gốc
D. Gọi `getStackTrace()` để lấy đúng đối tượng gốc
Đáp án đúng: A

Câu 19. `Constructor.newInstance(args)` thực hiện thao tác gì?
A. Chỉ trả về metadata `Class` của kiểu được tạo
B. Chỉ chạy method `main` của lớp được chọn
C. Chạy constructor để tạo instance mới
D. Chỉ kiểm tra tham số, không chạy constructor
Đáp án đúng: C

Câu 20. Vì sao thường dùng `getDeclaredConstructor().newInstance()` thay `Class.newInstance()`?
A. Cho phép tạo instance của lớp abstract bất kỳ
B. Bỏ mọi ràng buộc module cho constructor private
C. Bỏ hết checked exception do constructor khai báo
D. Chọn constructor và bọc lỗi do nó ném
Đáp án đúng: D

Câu 21. Trong ứng dụng có Java Modules, `setAccessible(true)` có giới hạn nào?
A. Luôn truy cập được mọi member private của module
B. Bắt buộc đổi field sang public rồi mới gọi được
C. Chỉ có tác dụng với method và field static
D. Có thể bị từ chối nếu package chưa mở phù hợp
Đáp án đúng: D

Câu 22. `trySetAccessible()` xử lý trường hợp quyền truy cập không thể bật như thế nào?
A. Trả `false` nếu không bật được quyền truy cập
B. Luôn trả `true`, bỏ qua mọi giới hạn của module
C. Chỉ kiểm tra constructor public trong cùng module
D. Luôn ném `InaccessibleObjectException` khi bị chặn
Đáp án đúng: A

Câu 23. `field.canAccess(obj)` dùng để xác định điều gì?
A. Kiểm tra object có field cùng tên đang tồn tại
B. Kiểm tra quyền truy cập hiện hành mà không sửa quyền
C. Đổi quyền truy cập của field thành public tạm thời
D. Tự bật quyền truy cập private như `setAccessible`
Đáp án đúng: B

Câu 24. Khai báo `exports p;` trong `module-info.java` có ý nghĩa gì?
A. Biến toàn bộ lớp trong package `p` thành public
B. Cho module khác sửa field final của package `p`
C. Mở toàn bộ member private của `p` cho mọi module
D. Cho module khác dùng API public trong package `p`
Đáp án đúng: D

Câu 25. Khai báo `opens p;` trong module Java hỗ trợ điều gì?
A. Cho phép deep reflection vào package `p` lúc runtime
B. Biến tất cả method private của package `p` thành public
C. Chỉ công khai API public của package `p` khi biên dịch
D. Tự đổi thư mục chứa mã nguồn của package `p`
Đáp án đúng: A

Câu 26. Tùy chọn JVM `--add-opens m/p=target` dùng cho tình huống nào?
A. Mở package `p` của module `m` cho module `target`
B. Chuyển package `p` sang một module mới `target`
C. Export public API của `p` khi biên dịch module `m`
D. Thêm một quan hệ `requires` giữa các module
Đáp án đúng: A

Câu 27. `module.isOpen("p", otherModule)` kiểm tra điều gì?
A. ClassLoader đã nạp mọi class của package `p`
B. Kiểm tra `p` có mở cho `otherModule` hay không
C. Mọi class khai báo trong `p` đều là class public
D. Một method private trong `p` đã chạy hay chưa
Đáp án đúng: B

Câu 28. Vì sao `@Retention(RetentionPolicy.RUNTIME)` quan trọng với Reflection?
A. Annotation chỉ tồn tại trong source trước biên dịch
B. Annotation còn sẵn để đọc tại thời điểm runtime
C. Annotation chỉ tồn tại ở class file, mất khi chạy
D. Annotation tự động được kế thừa bởi mọi lớp con
Đáp án đúng: B

Câu 29. `getDeclaredAnnotation(Flag.class)` lấy annotation theo phạm vi nào?
A. Lấy annotation từ mọi lớp cha dù không `@Inherited`
B. Lấy annotation từ tất cả phần tử trong package
C. Lấy annotation từ mọi field của lớp đang xét
D. Chỉ lấy annotation được khai báo ngay trên phần tử
Đáp án đúng: D

Câu 30. `@Inherited` trên một loại annotation có tác dụng gì?
A. Cho method override thừa hưởng annotation của method cha
B. Cho interface con thừa hưởng annotation của interface cha
C. Có thể cho lớp con thừa hưởng annotation trên lớp cha
D. Cho field trùng tên thừa hưởng annotation của field cha
Đáp án đúng: C

Câu 31. `@Repeatable(Container.class)` được dùng cho trường hợp nào?
A. Cho phép lặp annotation trên cùng một phần tử
B. Chỉ giữ annotation trong source mà không đưa vào class
C. Cho phép thay thế mọi annotation khác lúc runtime
D. Cho phép một annotation dùng lại qua nhiều ClassLoader
Đáp án đúng: A

Câu 32. `getAnnotationsByType(Tag.class)` có ích với annotation repeatable ra sao?
A. Lấy nhiều `Tag` cùng kiểu, gồm các `Tag` lặp lại
B. Lấy method của annotation dưới dạng `String[]`
C. Lấy annotation từ toàn bộ field của class
D. Lấy mọi annotation khác kiểu dưới dạng `Object[]`
Đáp án đúng: A

Câu 33. Mục đích của `@Target(ElementType.TYPE_USE)` là gì?
A. Chỉ cho phép annotation gắn trên khai báo field
B. Chỉ cho phép annotation gắn trên khai báo module
C. Cho phép annotation gắn vào vị trí sử dụng một kiểu
D. Chỉ cho phép annotation gắn trên khai báo method
Đáp án đúng: C

Câu 34. `Parameter.isNamePresent()` kiểm tra đặc điểm nào của metadata?
A. Parameter có được đánh dấu `final` trong source không
B. Parameter có giá trị mặc định khi gọi method hay không
C. Parameter có annotation runtime đi kèm hay không
D. Tên thật của parameter có được lưu trong class file
Đáp án đúng: D

Câu 35. Khi biên dịch Java, tùy chọn `javac -parameters` giúp ích gì cho Reflection?
A. Lưu tên parameter của method và constructor vào class file
B. Cho phép truy cập mọi field private giữa các module
C. Lưu giá trị runtime của mọi biến cục bộ vào class file
D. Tắt type erasure với các parameter generic của lớp
Đáp án đúng: A

Câu 36. `Method.getGenericReturnType()` khác `getReturnType()` ở điểm gì?
A. Trả `Type` suy ra từ object kết quả lúc runtime
B. Trả giá trị thực sau khi method được thực thi
C. Trả `Class<?>` đã loại bỏ thông tin generic
D. Trả `Type` có thể giữ metadata generic của kiểu trả về
Đáp án đúng: D

Câu 37. Với field khai báo `List<String> items`, `getGenericType()` có thể trả kiểu gì?
A. `Class<List<String>>` chứa đầy đủ generic runtime
B. `ParameterizedType` với đối số kiểu `String`
C. `Class<String>` vì chỉ xét kiểu phần tử
D. `TypeVariable` luôn đại diện cho lớp `String`
Đáp án đúng: B

Câu 38. `ParameterizedType.getActualTypeArguments()` cho phép lấy thông tin nào?
A. Các phần tử runtime của collection dạng `Object[]`
B. Các field được khai báo trong kiểu generic được chọn
C. Giá trị runtime của từng biến kiểu trong instance
D. Các đối số kiểu generic được khai báo dạng `Type[]`
Đáp án đúng: D

Câu 39. Với `Box<T>` và một instance, điều gì đúng về type erasure?
A. Reflection luôn đọc được `String` từ `Box<String>`
B. JVM tự lưu `T` trong mọi object header của Box
C. Không luôn suy ra đối số `T` cụ thể chỉ từ instance
D. Mọi biến cục bộ đều lưu đối số `T` ở runtime
Đáp án đúng: C

Câu 40. `Array.newInstance(int.class, 3)` trả về loại đối tượng nào?
A. Tạo mảng `Integer[]` với độ dài bằng `3`
B. Tạo mảng `byte[]` rồi tự ép thành `int[]`
C. Tạo đối tượng `Integer` với giá trị bằng `3`
D. Tạo mảng `int[]` với độ dài bằng `3`
Đáp án đúng: D

Câu 41. `Array.get(array, index)` với mảng primitive có thể trả kết quả nào?
A. Tham chiếu trực tiếp tới một biến primitive
B. Giá trị phần tử được boxing thành wrapper tương ứng
C. Một mảng mới chỉ chứa phần tử được chọn
D. Con trỏ native trỏ trực tiếp vào vùng nhớ mảng
Đáp án đúng: B

Câu 42. `Proxy.newProxyInstance(...)` của JDK tạo proxy theo cơ chế nào?
A. Thay đổi bytecode gốc của class được ủy quyền
B. Tạo proxy cho method private của mọi class
C. Tạo đối tượng triển khai những interface được chỉ định
D. Tạo subclass bất kỳ kể cả class final không interface
Đáp án đúng: C

Câu 43. Trong dynamic proxy JDK, `InvocationHandler.invoke(...)` có vai trò gì?
A. Luôn gọi method gốc, không thể đổi hành vi xử lý
B. Chỉ chạy một lần khi proxy được tạo, trước mọi method
C. Nhận lời gọi method qua proxy để quyết định cách xử lý
D. Chỉ được gọi khi khởi tạo constructor của lớp đích
Đáp án đúng: C

Câu 44. Khi gọi `equals`, `hashCode`, `toString` trên dynamic proxy JDK, điều gì đúng?
A. Những lời gọi này chỉ chạy nếu interface khai báo lại
B. Những lời gọi này luôn đi thẳng tới `Object` của proxy
C. Những lời gọi này tự mất khi proxy có nhiều interface
D. Những lời gọi này cũng được đưa qua `InvocationHandler`
Đáp án đúng: D

Câu 45. `Proxy.isProxyClass(clazz)` kiểm tra đặc điểm gì của lớp?
A. Lớp được tải bằng một ClassLoader tự định nghĩa
B. Lớp có triển khai ít nhất hai interface tùy ý
C. Lớp được tạo bởi cơ chế dynamic proxy của JDK
D. Lớp có annotation tên `Proxy` được giữ runtime
Đáp án đúng: C

Câu 46. Với một lớp `record` Java, `getRecordComponents()` trả về gì?
A. Metadata của những record component được khai báo
B. Mọi field instance của record và các lớp cha
C. Metadata của mọi constructor có trong record
D. Mọi method public được kế thừa từ lớp `Record`
Đáp án đúng: A

Câu 47. Với class khai báo `sealed`, `getPermittedSubclasses()` cung cấp thông tin nào?
A. Mọi lớp con hiện đã tạo instance trong JVM
B. Chỉ những lớp có constructor public trong module
C. Danh sách những method final của từng subclass
D. Các lớp hoặc interface được khai báo là permitted subclass
Đáp án đúng: D

Câu 48. Khi xây dựng công cụ gọi method bằng Reflection nhiều lần, cách nào phù hợp?
A. Tìm lại mọi method bằng `getDeclaredMethods()` trước mỗi lần
B. Bật `setAccessible(true)` cho mọi member của mọi lớp
C. Tái sử dụng metadata đã tra cứu và giới hạn quyền truy cập
D. Bỏ xử lý lỗi `Method.invoke` trong môi trường production
Đáp án đúng: C
