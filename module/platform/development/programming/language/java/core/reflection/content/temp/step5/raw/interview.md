Bạn mô tả Reflection API trong Java cho phép quan sát và thao tác những thông tin nào tại runtime, đồng thời khác lời gọi mã tĩnh ra sao?
Bạn lựa chọn reflection thay vì interface, generics hoặc dependency injection tĩnh trong một công cụ Java dựa trên tiêu chí nào?
Bạn phân biệt class literal, `Object.getClass()` và `Class.forName()` khi lấy đối tượng `Class` ra sao?
Bạn giải thích sự khác nhau giữa việc tải lớp, liên kết lớp và khởi tạo lớp khi một chương trình dùng reflection như thế nào?
Bạn kiểm tra tác động của `Class.forName` tới static initializer và cách tránh khởi tạo lớp khi chỉ cần metadata như thế nào?
Bạn sử dụng `ClassLoader.loadClass` để nạp lớp được chọn bằng cấu hình và kiểm soát class loader phù hợp ra sao?
Bạn xác định vì sao hai lớp có cùng tên đầy đủ nhưng do hai class loader khác nhau định nghĩa lại không tương thích kiểu như thế nào?
Bạn thiết kế bộ đăng ký plugin dùng tên lớp mà vẫn kiểm tra class được nạp có triển khai interface bắt buộc như thế nào?
Bạn phân biệt `Class.getName`, `getCanonicalName`, `getSimpleName` và `getTypeName` khi xây dựng công cụ hiển thị kiểu ra sao?
Bạn nhận diện các kiểu primitive, array, interface, enum và annotation bằng các phương thức kiểm tra trên `Class` như thế nào?
Bạn phân biệt `Class.isInstance` với `Class.isAssignableFrom` khi kiểm tra khả năng gán kiểu động như thế nào?
Bạn xử lý khác biệt giữa kiểu primitive và wrapper khi một hệ thống nhận tham số phương thức bằng reflection ra sao?
Bạn truy xuất superclass và các interface được một lớp triển khai trực tiếp, đồng thời xử lý quan hệ kế thừa như thế nào?
Bạn dùng `getSuperclass` và `getGenericSuperclass` khi cần bảo toàn thông tin kiểu của lớp cha như thế nào?
Bạn phân biệt nested class, member class, local class và anonymous class khi phản chiếu metadata như thế nào?
Bạn truy vấn enclosing class, enclosing method hoặc enclosing constructor để chẩn đoán nguồn gốc của một lớp lồng nhau ra sao?
Bạn nhận diện record class và khai thác `RecordComponent` để xây dựng công cụ ánh xạ dữ liệu như thế nào?
Bạn kiểm tra sealed class và các lớp con được cho phép ở runtime bằng Reflection API như thế nào?
Bạn đọc các modifier `public`, `private`, `static`, `final` hoặc `abstract` của lớp và thành viên bằng cách nào?
Bạn giải thích vì sao thứ tự phần tử trả về từ các phương thức `getDeclaredMethods` hoặc `getDeclaredFields` không nên được giả định là thứ tự mã nguồn như thế nào?
Bạn phân biệt `getFields` và `getDeclaredFields` khi cần truy xuất field được kế thừa và field không public như thế nào?
Bạn xác định cách tìm một field khai báo ở superclass khi `getDeclaredField` trên subclass không trả về kết quả như thế nào?
Bạn phân biệt `getMethods` và `getDeclaredMethods` về phương thức được kế thừa và mức truy cập như thế nào?
Bạn tìm đúng phương thức bị overload dựa trên tên và danh sách kiểu tham số thông qua `getMethod` như thế nào?
Bạn giải thích vì sao kiểu trả về không được dùng để phân biệt các overload trong lời gọi `getMethod` ra sao?
Bạn xử lý `NoSuchFieldException` và `NoSuchMethodException` khi một phiên bản thư viện thay đổi chữ ký thành viên như thế nào?
Bạn nhận diện các synthetic member do compiler tạo ra và quyết định khi nào cần loại khỏi danh sách public API như thế nào?
Bạn phân biệt bridge method do generic type erasure với phương thức được lập trình viên khai báo khi duyệt reflection ra sao?
Bạn phân tích tình huống `Method` đại diện cho phương thức bị override và cách chọn implementation thực tế khi gọi trên một receiver như thế nào?
Bạn xác định sự khác nhau giữa `Method.getReturnType` và `getGenericReturnType` đối với phương thức trả về kiểu generic ra sao?
Bạn sử dụng `getParameterTypes` và `getGenericParameterTypes` để kiểm tra chữ ký phương thức khi có parameterized type như thế nào?
Bạn đọc tên tham số bằng `Parameter` và xác định giới hạn khi mã nguồn được biên dịch không có tùy chọn giữ tên tham số ra sao?
Bạn xử lý varargs method bằng reflection và phân biệt tham số mảng với các đối số truyền vào khi gọi động như thế nào?
Bạn đọc khai báo checked exception của phương thức qua `getExceptionTypes` hoặc `getGenericExceptionTypes` để phục vụ công cụ API như thế nào?
Bạn kiểm tra `Method.isDefault` để xác định phương thức mặc định trên interface và phân biệt với phương thức abstract như thế nào?
Bạn xác định cách truy xuất thông tin constructor public và constructor khai báo trực tiếp bằng `getConstructors` và `getDeclaredConstructors` ra sao?
Bạn tạo instance thông qua `Constructor.newInstance` và xử lý constructor có tham số như thế nào?
Bạn phân biệt ngoại lệ khi không tìm thấy constructor, không đủ quyền truy cập và constructor tự ném lỗi ra sao?
Bạn giải thích vì sao `Class.newInstance` không còn là lựa chọn phù hợp so với reflection trên `Constructor` trong mã Java hiện đại như thế nào?
Bạn thiết kế cơ chế chọn constructor để dependency injection có thể xử lý nhiều constructor hoặc annotation đánh dấu constructor ra sao?
Bạn kiểm tra các loại class không thể tạo instance bằng constructor thông thường, chẳng hạn interface hoặc abstract class, như thế nào?
Bạn lựa chọn thời điểm khởi tạo đối tượng mặc định, khởi tạo qua factory và dùng reflection để tránh tác dụng phụ của constructor ra sao?
Bạn đọc giá trị một instance field và một static field qua `Field.get` theo đúng receiver như thế nào?
Bạn ghi giá trị field bằng `Field.set` và kiểm tra tương thích kiểu dữ liệu, primitive conversion hoặc null ra sao?
Bạn phân biệt `Field.getType` và `getGenericType` khi field có kiểu `List` chứa phần tử generic như thế nào?
Bạn đánh giá rủi ro khi reflection sửa một field final hoặc static final đối với tính đúng đắn và các tối ưu JVM như thế nào?
Bạn thiết kế một serializer chỉ đọc field phù hợp mà không phụ thuộc vào việc truy cập trực tiếp tất cả thành viên private ra sao?
Bạn lựa chọn gọi getter qua `Method.invoke` hay truy cập field trực tiếp khi xây dựng thư viện mapping dữ liệu như thế nào?
Bạn truyền receiver và danh sách argument vào `Method.invoke` để gọi instance method, static method và method trả về void như thế nào?
Bạn phân biệt `IllegalArgumentException` từ lời gọi reflection với `InvocationTargetException` chứa ngoại lệ do phương thức đích ném ra ra sao?
Bạn bảo toàn nguyên nhân gốc và stack trace khi chuyển đổi `InvocationTargetException` thành lỗi có ngữ nghĩa của framework như thế nào?
Bạn nhận diện và xử lý `ExceptionInInitializerError` khi thao tác reflection kích hoạt khởi tạo class thất bại như thế nào?
Bạn kiểm tra một lời gọi `Method.invoke` cần boxing hoặc unboxing tham số và kết quả trước khi xây dựng adapter như thế nào?
Bạn thiết kế bộ cache cho `Method`, `Field` và `Constructor` để giảm lookup lặp lại trong đường chạy nóng ra sao?
Bạn xác định nguy cơ class loader leak khi cache object `Class` hoặc `Method` trong một registry có vòng đời dài như thế nào?
Bạn cân nhắc `ClassValue` hoặc cache gắn vòng đời class loader để lưu metadata reflection an toàn như thế nào?
Bạn phân biệt array class với component type khi một API reflection phải xử lý cả mảng primitive và mảng object ra sao?
Bạn sử dụng `java.lang.reflect.Array` để tạo mảng với component type chỉ được biết tại runtime như thế nào?
Bạn đọc và cập nhật phần tử mảng bằng `Array.get` và `Array.set` rồi xử lý trường hợp sai kiểu hoặc vượt chỉ số ra sao?
Bạn xác định cách kiểm tra mảng đa chiều và component type của từng cấp mảng bằng reflection như thế nào?
Bạn giải thích type erasure làm mất thông tin nào và giữ lại thông tin nào trong các chữ ký generic được phản chiếu ra sao?
Bạn phân biệt `Type`, `Class`, `ParameterizedType`, `TypeVariable` và `WildcardType` khi phân tích generic type như thế nào?
Bạn đọc danh sách type argument của một field kiểu `Map<String, List<Integer>>` qua API reflection như thế nào?
Bạn xác định upper bound và lower bound của wildcard generic khi sinh schema từ một chữ ký phương thức ra sao?
Bạn phân biệt type parameter khai báo trên class với type parameter khai báo riêng trên method bằng reflection như thế nào?
Bạn sử dụng `GenericArrayType` để xử lý chữ ký mảng có component type là type variable hoặc parameterized type ra sao?
Bạn giải thích vì sao không thể suy ra chắc chắn kiểu phần tử generic chỉ từ runtime class của một `ArrayList` như thế nào?
Bạn thiết kế một cấu trúc tương đương type token để bảo toàn thông tin `Type` trong API có generic parameter ra sao?
Bạn xử lý một `TypeVariable` có nhiều bound và theo dõi quan hệ với declaration chứa nó như thế nào?
Bạn kiểm tra lỗi `TypeNotPresentException` hoặc malformed generic signature khi dependency runtime không còn tương thích như thế nào?
Bạn phân biệt raw type và parameterized type khi sinh mô hình dữ liệu cho framework serialization như thế nào?
Bạn giải thích vai trò của `AnnotatedElement` khi truy vấn annotation trên class, method, field và constructor như thế nào?
Bạn phân biệt `getAnnotation`, `getDeclaredAnnotation` và `isAnnotationPresent` khi metadata có quy tắc kế thừa ra sao?
Bạn xác định vì sao annotation có retention `CLASS` hoặc `SOURCE` không thể được truy vấn trực tiếp bằng reflection thông thường như thế nào?
Bạn thiết kế annotation `RUNTIME` dùng trong framework và kiểm tra phạm vi áp dụng qua `@Target` ra sao?
Bạn sử dụng `getAnnotationsByType` để đọc repeatable annotation và đánh giá tác động của annotation container như thế nào?
Bạn phân tích ý nghĩa của `@Inherited` khi tra cứu annotation trên class con so với annotation trên interface hoặc method như thế nào?
Bạn đọc annotation trên tham số phương thức hoặc constructor và xác định đúng tham số tương ứng bằng API nào?
Bạn phân biệt declaration annotation với type-use annotation khi đọc `AnnotatedType` qua reflection như thế nào?
Bạn truy cập annotation trên generic type argument, array component và type bound thông qua các subtype của `AnnotatedType` như thế nào?
Bạn xử lý annotation element có giá trị là `Class` hoặc enum đã bị loại khỏi classpath ở runtime như thế nào?
Bạn xây dựng bộ validate dữ liệu từ annotation và thông báo lỗi rõ ràng khi một trường bắt buộc không có metadata phù hợp ra sao?
Bạn giải thích vì sao `setAccessible(true)` không mặc nhiên vượt qua mọi ranh giới truy cập của JPMS trong Java hiện đại như thế nào?
Bạn phân biệt `exports` và `opens` trong module descriptor khi một framework cần gọi public API hoặc truy cập sâu bằng reflection ra sao?
Bạn chẩn đoán `InaccessibleObjectException` khi truy cập private member của một package chưa được mở trong module như thế nào?
Bạn sử dụng `trySetAccessible` để kiểm tra quyền truy cập mà không để toàn bộ quy trình lỗi ngay khi yêu cầu bị từ chối như thế nào?
Bạn kiểm tra `AccessibleObject.canAccess` với receiver phù hợp trước khi gọi một thành viên phản chiếu ra sao?
Bạn đánh giá cách dùng `--add-opens` như một giải pháp chuyển tiếp và kế hoạch loại bỏ phụ thuộc vào truy cập nội bộ như thế nào?
Bạn xác định liệu một package được export nhưng không open có cho phép framework truy cập private field bằng reflection hay không bằng cách nào?
Bạn thiết kế module công bố đúng phần API cần thiết cho thư viện reflection thay vì mở toàn bộ package như thế nào?
Bạn giải thích vai trò của `MethodHandles.Lookup` và quyền truy cập gắn với lookup khi so sánh với `Method.invoke` như thế nào?
Bạn dùng `MethodHandles.privateLookupIn` trong điều kiện module cho phép và phân biệt nó với việc tự ý vượt qua kiểm soát truy cập ra sao?
Bạn lựa chọn `MethodHandle` hoặc `VarHandle` thay cho reflection truyền thống khi thao tác cần gọi hoặc truy cập field nhiều lần như thế nào?
Bạn đánh giá việc sử dụng `Lookup.unreflect` để tạo method handle từ đối tượng `Method` đã phát hiện qua reflection ra sao?
Bạn giải thích cách `Proxy.newProxyInstance` tạo implementation của một tập interface được chọn ở runtime như thế nào?
Bạn thiết kế `InvocationHandler` để điều hướng lời gọi và giữ nguyên ngữ nghĩa của argument, kết quả cùng ngoại lệ như thế nào?
Bạn phân biệt trường hợp JDK dynamic proxy phù hợp với interface và trường hợp framework cần tạo subclass cho concrete class ra sao?
Bạn xử lý `equals`, `hashCode` và `toString` trên dynamic proxy để tránh lỗi trong registry hoặc collection như thế nào?
Bạn giải thích điều kiện xuất hiện `UndeclaredThrowableException` khi `InvocationHandler` ném checked exception như thế nào?
Bạn gọi default method của interface từ dynamic proxy bằng cơ chế được JDK hỗ trợ và kiểm tra quyền truy cập như thế nào?
Bạn đánh giá tác động của class loader và tính hiển thị interface khi tạo proxy cho plugin nằm trong class loader riêng ra sao?
Bạn thiết kế proxy đo thời gian xử lý hoặc kiểm tra quyền mà không ghi lộ dữ liệu nhạy cảm hay thay đổi kết quả lời gọi ra sao?
Bạn phân biệt proxy động với decorator viết tĩnh về chi phí, tính linh hoạt và khả năng bảo trì như thế nào?
Bạn xác định những nguy cơ khi nhận tên class hoặc method trực tiếp từ cấu hình không tin cậy rồi gọi reflection ra sao?
Bạn thiết kế danh sách cho phép cho những class và method được kích hoạt từ đầu vào bên ngoài như thế nào?
Bạn giải thích vì sao giới hạn truy cập của module hoặc class loader không tương đương với một sandbox an toàn cho plugin độc hại như thế nào?
Bạn xử lý lỗi do reflection gọi mã của bên thứ ba có side effect hoặc chạy lâu bằng cách thiết kế ranh giới thực thi như thế nào?
Bạn kiểm tra rủi ro thay đổi implementation nội bộ hoặc tên field khi một thư viện serialization phụ thuộc sâu vào reflection như thế nào?
Bạn thiết kế contract test cho công cụ mapping dùng reflection để phát hiện thay đổi getter, constructor và annotation khi nâng cấp thư viện ra sao?
Bạn xây dựng bộ kiểm thử cho các trường hợp overloaded method, inherited method, generic bridge method và private access như thế nào?
Bạn kiểm thử reflection trên record, enum, sealed class và array để tránh giả định rằng mọi kiểu đều có constructor thông thường ra sao?
Bạn đo chi phí lookup và invocation riêng biệt trong benchmark reflection để so sánh công bằng với lời gọi trực tiếp như thế nào?
Bạn giải thích ảnh hưởng của warm-up, JIT và cache metadata khi benchmark `Method.invoke` trong một ứng dụng Java như thế nào?
Bạn thiết kế cách quan sát thời gian khởi tạo class, số class được nạp và metadata khi framework dùng reflection trên quy mô lớn ra sao?
Bạn phân tích giới hạn của reflection khi biên dịch native image hoặc AOT và thiết kế metadata cấu hình phù hợp như thế nào?
Bạn lựa chọn giữa reflection, annotation processing và code generation khi tạo serializer hoặc dependency injection container dựa trên tiêu chí nào?
Bạn xây dựng chiến lược giảm phụ thuộc vào tên thành viên dưới dạng chuỗi để việc refactor không làm hỏng mã reflection như thế nào?
Bạn đánh giá một thiết kế sử dụng reflection theo các tiêu chí độ an toàn kiểu, hiệu năng, kiểm soát truy cập và khả năng kiểm thử như thế nào?
