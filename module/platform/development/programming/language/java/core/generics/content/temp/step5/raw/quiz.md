Câu 1. Với `class Box<T> { T value; }`, lợi ích trực tiếp của `Box<String>` là gì?
A. JVM tạo một class file riêng cho từng T được dùng.
B. Compiler kiểm tra kiểu String khi gán và đọc qua Box.
C. Compiler bỏ qua cast vì Box luôn lưu String ở runtime.
D. JVM kiểm tra generic argument bằng reflection mỗi lần đọc.
Đáp án đúng: B

Câu 2. Tại sao gán `List<String>` cho biến `List<Object>` không hợp lệ trong Java?
A. JVM không hỗ trợ object String trong generic collection.
B. `String` không phải subtype của `Object` trong Java.
C. `List<Object>` chỉ dùng với collection không có phần tử.
D. `List<T>` invariant dù `String` kế thừa `Object`.
Đáp án đúng: D

Câu 3. Một biến `List<? extends CharSequence>` có thể nhận trực tiếp giá trị nào?
A. `List<String>` vì String thực hiện CharSequence.
B. `List<Object>` vì Object là supertype của String.
C. `List<Number>` vì Number là superclass của số.
D. `List<Integer>` vì Integer thuộc các wrapper class.
Đáp án đúng: A

Câu 4. Khi đọc `items.get(0)` từ biến `List<?> items`, kiểu tĩnh an toàn nhất là gì?
A. `Number` vì compiler chọn cận trên của wildcard.
B. `void` vì không thể lấy phần tử từ wildcard.
C. `String` vì wildcard suy luận kiểu tại runtime.
D. `Object` vì kiểu phần tử wildcard chưa xác định.
Đáp án đúng: D

Câu 5. Không dùng raw cast, thao tác thêm nào hợp lệ với một `List<?> values`?
A. `values.add(1)` vì wildcard chấp nhận mọi wrapper.
B. `values.add(null)` vì null hợp lệ với wildcard.
C. `values.add("x")` nếu list hiện có các chuỗi.
D. `values.add(new Object())` vì Object là kiểu gốc.
Đáp án đúng: B

Câu 6. Với `List<? extends Number> source`, phép đọc nào được compiler chấp nhận?
A. Gán `Double n = source.get(0)` không cần cast.
B. Gán `Integer n = source.get(0)` không cần cast.
C. Gán `Number n = source.get(0)` từ danh sách.
D. Gán `String n = source.get(0)` không cần cast.
Đáp án đúng: C

Câu 7. Tại sao `source.add(1)` không hợp lệ nếu `source` có kiểu `List<? extends Number>`?
A. Phương thức add bị xóa khỏi API khi dùng wildcard.
B. Wildcard extends biến mọi List thành bất biến runtime.
C. Kiểu phần tử có thể là subtype Number khác Integer.
D. Integer không kế thừa Number nên bị từ chối.
Đáp án đúng: C

Câu 8. Với `List<? super Integer> target`, thao tác nào hợp lệ về kiểu?
A. `target.add(Integer.valueOf(3))` hợp lệ về kiểu.
B. Gán `Integer x = target.get(0)` mà không có cast.
C. Gọi `target.add(Double.valueOf(3))` trên danh sách.
D. Gán `Number x = target.get(0)` mà không có cast.
Đáp án đúng: A

Câu 9. Đọc `target.get(0)` từ `List<? super Integer>` trực tiếp vào biến kiểu nào là an toàn?
A. `Integer` vì wildcard super lưu đúng mỗi Integer.
B. `String` vì phần tử thực tế sẽ được cast tự động.
C. `Object` do kiểu phần tử có thể là Object.
D. `Number` vì mọi supertype Integer đều là Number.
Đáp án đúng: C

Câu 10. Trong quy tắc PECS của Java generics, ý nghĩa đúng là gì?
A. Producer dùng super; consumer dùng extends theo PECS.
B. Đọc và ghi T đều dùng extends cho cùng một List.
C. Đọc và ghi T đều dùng super để giữ subtype.
D. Producer dùng extends; consumer dùng super theo PECS.
Đáp án đúng: D

Câu 11. Khai báo nào định nghĩa đúng một static generic method trả lại đối số của nó?
A. `static <T> T echo(T v) { return v; }`.
B. `static T echo<T>(T v) { return v; }`.
C. `static T <T> echo(T v) { return v; }`.
D. `static T echo(T v) { return v; }`.
Đáp án đúng: A

Câu 12. Với `<T extends Number> void accept(T value)`, lời gọi nào phù hợp mà không sửa type bound?
A. Gọi `accept(Integer.valueOf(5))` với type bound Number.
B. Gọi `accept(new StringBuilder("5"))` vì có ký tự số.
C. Gọi `accept("5")` vì String chuyển đổi thành Number.
D. Gọi `accept(new Object())` vì Object là root type.
Đáp án đúng: A

Câu 13. Muốn ràng buộc `T` vừa là subtype của Number vừa thực hiện Comparable<T>, khai báo nào đúng?
A. `<T implements Number & Comparable<T>>` cho type variable.
B. `<T extends Comparable<T> & Number>` đặt class cuối.
C. `<T super Number & Comparable<T>>` cho type variable.
D. `<T extends Number & Comparable<T>>` đúng thứ tự bound.
Đáp án đúng: D

Câu 14. Với `class Holder<T>`, tại sao không thể khai báo `static T cached;`?
A. Static field chỉ được chứa primitive trong generic class.
B. Static member của generic class bị JVM cấm toàn bộ.
C. Type parameter T chỉ dùng trong constructor generic class.
D. Static field không thể dùng type parameter T của class.
Đáp án đúng: D

Câu 15. Vì sao `new T()` không hợp lệ trong `class Factory<T>` thông thường?
A. Object tạo bởi `new T()` có thể bị GC ngay sau khởi tạo.
B. Erasure không biết constructor T để gọi `new T()`.
C. Type parameter T bắt buộc phải là interface abstract.
D. Constructor của kiểu T chỉ được gọi từ static method.
Đáp án đúng: B

Câu 16. Vì sao `new List<String>[2]` bị cấm khi tạo mảng generic?
A. JVM giới hạn mảng generic ở độ dài lớn hơn hai phần tử.
B. `List<String>` không reifiable để làm component type của array.
C. Array chỉ chứa primitive và không giữ được List object.
D. List<String> luôn ở native memory thay vì heap.
Đáp án đúng: B

Câu 17. Trong Java, biểu thức tạo mảng nào hợp lệ về reifiability?
A. `new List<? super Integer>[2]` vì Integer là final.
B. `new List<String>[2]` vì String là kiểu reifiable.
C. `new List<?>[2]` vì wildcard unbounded là reifiable.
D. `new List<? extends Number>[2]` vì Number là class.
Đáp án đúng: C

Câu 18. Với `Object obj`, kiểm tra `obj instanceof List<?>` có hợp lệ không?
A. Có, nhưng runtime xác minh type argument từng phần tử.
B. Không, vì wildcard chỉ dùng trong khai báo phương thức.
C. Không, vì mọi parameterized type bị cấm sau instanceof.
D. Có, vì `List<?>` là dạng reifiable cho phép kiểm tra.
Đáp án đúng: D

Câu 19. Hai object `new ArrayList<String>()` và `new ArrayList<Integer>()` có `getClass()` như thế nào?
A. Object thứ hai nhận class runtime của Number.
B. Cùng runtime class `ArrayList` sau khi type erasure.
C. Hai class runtime khác nhau ứng với String và Integer.
D. Class runtime được chọn theo kiểu phần tử đầu tiên.
Đáp án đúng: B

Câu 20. Với `class Cache<T extends Number>`, T thường bị erasure thành kiểu nào?
A. `Object` bất kể upper bound đã khai báo.
B. `Number` vì đó là upper bound đầu tiên.
C. `Class<T>` vì runtime giữ generic type argument.
D. `Integer` vì subtype Number thường được dùng.
Đáp án đúng: B

Câu 21. Vì sao không thể overload hai method `print(List<String>)` và `print(List<Integer>)` trong một class?
A. Cả hai có cùng erased parameter signature `print(List)`.
B. Java cấm mọi method overload nhận cùng một generic class.
C. Compiler chọn method bằng generic type argument ở runtime.
D. `List<String>` và `List<Integer>` có cùng số phần tử.
Đáp án đúng: A

Câu 22. Bridge method do Java compiler sinh thường phục vụ mục đích gì?
A. Thay mọi cast không an toàn bằng kiểm tra vùng nhớ GC.
B. Tạo class riêng cho từng instantiation của generic type.
C. Giữ overriding hoạt động sau erasure của method generic.
D. Cho phép runtime suy ra chính xác type argument của List.
Đáp án đúng: C

Câu 23. Khi truyền `List<String>` vào biến raw `List raw`, điều gì xảy ra nếu gọi `raw.add(42)`?
A. JVM tự đổi Integer 42 thành String trước khi thêm.
B. Compiler luôn từ chối vì raw type không có method add.
C. JVM tạo bản sao List<Integer> độc lập cho raw.
D. Compile kèm unchecked warning, có nguy cơ heap pollution.
Đáp án đúng: D

Câu 24. Một `List<String>` ban đầu rỗng bị thêm `Integer` qua `raw.add(42)`; sau đó gọi `String s = list.get(0)` có thể gặp gì?
A. `NoSuchMethodError` do erasure xóa method get.
B. `ClassCastException` ở cast khi đọc phần tử sai kiểu.
C. `VerifyError` khi bytecode gọi getter có generic type.
D. `ArrayStoreException` khi JVM ghi vào object List.
Đáp án đúng: B

Câu 25. Với `List<String> names = new ArrayList<>();`, diamond operator suy luận type argument thế nào?
A. Suy ra kiểu từ phần tử đầu tiên thêm vào sau.
B. String được suy luận từ target type khi dùng diamond.
C. Suy ra CharSequence từ superclass của String.
D. Suy ra Object bất kể biến đích được khai báo.
Đáp án đúng: B

Câu 26. Với `List<String> names = Collections.emptyList();`, generic method chọn kiểu phần tử ra sao?
A. Compiler có thể suy luận String từ ngữ cảnh gán.
B. Method cần một phần tử String để suy ra T.
C. Method chỉ trả List<Object> và cần cast thủ công.
D. Runtime kiểm tra List trống rồi chọn kiểu String.
Đáp án đúng: A

Câu 27. Một helper `<T> void swap(List<T>, int, int)` có thể hỗ trợ `swapUnknown(List<?> xs)` bằng cách nào?
A. Đổi `List<?>` thành raw List để tránh kiểm tra kiểu.
B. Chuyển `xs` sang `List<Object>` bằng phép gán trực tiếp.
C. Gọi helper generic để capture kiểu phần tử của `xs`.
D. Dùng `xs.set(i, xs.get(j))` ngay trong method wildcard.
Đáp án đúng: C

Câu 28. Varargs kiểu `List<String>...` có thể dẫn đến vấn đề nào ở Java?
A. List<String> mất khả năng gọi get khi vào varargs.
B. Compiler luôn chặn tất cả method dùng generic varargs.
C. Varargs generic có thể gây heap pollution sau erasure.
D. JVM khởi tạo mảng String thay cho array chứa List.
Đáp án đúng: C

Câu 29. Với Java 17, `@SafeVarargs` dùng đúng trong tình huống nào?
A. Gắn lên method để JVM tự chặn heap pollution runtime.
B. Gắn lên mọi overridable instance method varargs generic.
C. Gắn lên method có fixed parameters nhưng không có varargs.
D. Gắn lên static method varargs generic thực sự an toàn.
Đáp án đúng: D

Câu 30. Khi field khai báo `List<String> names`, reflection có thể lấy type argument đã khai báo bằng cách nào?
A. Dùng `field.getType().getTypeParameters()` để lấy String.
B. Dùng JVM classpath để suy ra type argument T.
C. Dùng `Field.getGenericType()` và `ParameterizedType`.
D. Dùng `list.getClass()` để tìm String từ phần tử.
Đáp án đúng: C

Câu 31. Với `List<? super Number> target`, lời gọi thêm phần tử nào hợp lệ?
A. `target.add(Integer.valueOf(2))` được compiler chấp nhận.
B. `target.add(new Object())` vì Object là supertype.
C. Gán `Double n = target.get(0)` không cần cast.
D. Gán `Number n = target.get(0)` không cần cast.
Đáp án đúng: A

Câu 32. Để chép dữ liệu từ `List<String> src` sang `List<Object> dst` bằng `Collections.copy`, nhận định nào đúng?
A. Hợp lệ nếu dst đủ chỗ, vì dest super T và source extends T.
B. Không hợp lệ vì Collections.copy chỉ làm việc với cùng T.
C. Không hợp lệ vì List<String> không phải subtype List<Object>.
D. Hợp lệ ngay cả khi dst rỗng vì copy tự tăng kích thước.
Đáp án đúng: A
