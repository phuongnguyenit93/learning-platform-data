# Lựa chọn cách viết giúp người đọc nhận ra ý định: lambda và method reference trong Java

Khi đọc một đoạn Java dùng **lambda** (`->`) hoặc **method reference** (`::`), người bảo trì cần hiểu ngay: dữ liệu đi từ đâu đến đâu, đoạn code đang **biến đổi giá trị**, **kiểm tra điều kiện** hay **thực hiện side effect**, có xử lý ngoại lệ hoặc null không, và hành vi nào cần được giữ khi refactor. Cách viết tốt không phải là cách ngắn nhất; đó là cách giúp người đọc nhận ra **ý định và hợp đồng** với ít suy đoán nhất.

Ví dụ:

~~~java
names.stream().map(String::trim).toList();
names.stream().map(name -> name.trim()).toList();
~~~

Trong điều kiện các giá trị không null, hai cách trên có cùng ý nghĩa: **áp dụng phương thức `trim` lên từng chuỗi và tạo danh sách kết quả**. Method reference `String::trim` thường gọn và đúng trọng tâm vì không thêm logic nào. Nhưng khi có quy tắc nghiệp vụ:

~~~java
names.stream()
     .map(name -> name == null ? "" : name.trim())
     .toList();
~~~

lambda lại tốt hơn: người đọc nhìn thấy **chính sách null**. Thay dòng thứ ba bằng `String::trim` sẽ làm mất chính sách đó và có thể gây `NullPointerException`.

Bài học này tập trung vào **nguyên tắc lựa chọn hình thức dễ hiểu** trong phạm vi *Method reference*. Các quy tắc ngôn ngữ và API được nêu đều còn áp dụng trong Java hiện đại. Những API mới sau Java 8 sẽ được ghi phiên bản.

## 1. Câu hỏi trước khi quyết định dùng `::` hay `->`

Hãy đọc lời gọi bên ngoài trước, vì target functional interface quyết định ý nghĩa callback:

1. **Callback có nhiệm vụ gì?** `Function<T,R>` biến đổi một giá trị; `Predicate<T>` quyết định đúng/sai; `Consumer<T>` thực hiện hành động không trả kết quả; `Supplier<T>` cung cấp một giá trị.
2. **Đã có đúng một phương thức/constructor tên rõ nghĩa chưa?** Nếu có và việc ánh xạ tham số trực tiếp, method reference thường giúp giảm nhiễu.
3. **Có phải diễn tả thêm điều kiện, null, ngoại lệ, định dạng, toán tử hoặc phối hợp nhiều bước không?** Nếu có, lambda có thể trung thực với ý định hơn.
4. **Đối số nào là receiver?** `String::trim` nhận receiver từ tham số SAM, trong khi `object::method` đã cố định receiver. Viết ngắn nhưng đánh tráo receiver là sai.
5. **Có thay đổi thời điểm đánh giá receiver không?** `getService()::run` tính `getService()` khi tạo tham chiếu; `() -> getService().run()` tính khi gọi lambda.
6. **Code có được người khác đọc trong một pipeline dài không?** Nếu một chuỗi method references khiến mục đích bị che khuất, đặt tên helper hoặc tách biến trung gian rõ nghĩa.

Quy tắc thực dụng: **khi callback chỉ chuyển lời gọi thẳng đến một phương thức có tên biểu đạt hành vi, ưu tiên method reference**; **khi callback tự mang quyết định nghiệp vụ, ưu tiên lambda**. Đây là hướng dẫn về khả năng đọc, không phải ràng buộc cú pháp cứng.

## 2. So sánh bằng một bảng ra quyết định

| Tình huống | Dạng thường dễ đọc | Lý do |
| --- | --- | --- |
| Trim từng chuỗi không null | `.map(String::trim)` | Thao tác rõ ràng, một lời gọi |
| Parse chuỗi thành số nguyên | `.map(Integer::parseInt)` | Tên phương thức nói đúng biến đổi |
| In từng phần tử | `.forEach(System.out::println)` | Callback là hành động đơn |
| Ghi vào danh sách cụ thể | `items.forEach(auditLog::add)` | Receiver đã biết, side effect cố ý |
| Lấy thuộc tính từ object | `.map(User::email)` | Getter/accessor thể hiện nguồn dữ liệu |
| So sánh theo thuộc tính số | `Comparator.comparingInt(User::points)` | Tên comparator làm rõ mục tiêu |
| Tạo instance bằng constructor | `Supplier<ArrayList<String>> f = ArrayList::new;` | Chỉ cần gọi constructor |
| Đổi null thành giá trị mặc định | `x -> x == null ? "" : x.strip()` | Quy tắc nghiệp vụ hiện rõ |
| Ghép tên với điểm số | `u -> normalize(u.email()) + "=" + u.points()` | Phối hợp nhiều thao tác |
| Kiểm tra nhiều điều kiện | `u -> u.active() && u.points() >= 50` | Logic boolean quan trọng hơn cú pháp ngắn |
| Cần catch checked exception | `p -> { try { ... } catch (...) { ... } }` | Lambda có chỗ xử lý lỗi |
| Thêm một hằng số vào đầu vào | `s -> "prefix:" + s` | Tên receiver hay phép nối cần biểu đạt |
| Đảo thứ tự đối số | `(a,b) -> method(b,a)` | Reference có ánh xạ tham số khác |
| Receiver phải được lấy lại mỗi lần chạy | `x -> provider.get().send(x)` | Không được capture service quá sớm |
| Method overload khó hiểu | Lambda rõ tham số hoặc biến functional interface tường minh | Tránh người đọc phải tự suy diễn overload |

Các dòng là **minh họa**, không phải tất cả đều là chương trình độc lập; chúng giả định biến, phương thức, kiểu `User` hoặc `provider` đã tồn tại.

## 3. Method reference: để tên phương thức diễn đạt “làm gì”

Một method reference có bốn dạng thông dụng:

| Dạng | Ví dụ | Ý nghĩa dễ đọc |
| --- | --- | --- |
| Static method | `Integer::parseInt` | Gọi đúng phép parse của lớp |
| Instance method của object cụ thể | `System.out::println`, `log::add` | Gọi trên receiver đã chọn |
| Instance method của một kiểu | `String::trim`, `User::email` | Nhận receiver từ tham số callback |
| Constructor/array constructor | `ArrayList::new`, `String[]::new` | Tạo object/array khi callback được gọi |

Trong ngữ cảnh:

~~~java
List<String> raw = List.of(" 10 ", "20");
List<Integer> numbers = raw.stream()
    .map(String::trim)
    .map(Integer::parseInt)
    .toList();
~~~

Người đọc thấy ngay hai công đoạn: **làm sạch** rồi **chuyển sang số**. Không cần đặt biến lambda trung gian chỉ để đặt tên lại những phương thức vốn đã rõ ý định.

Tương tự:

~~~java
Comparator<String> byLength = Comparator.comparingInt(String::length);
~~~

Trong biểu thức này, `String::length` đóng vai hàm trích khóa sắp xếp kiểu `int`, còn `Comparator.comparingInt` cho biết phép so sánh dựa trên khóa đó. Viết:

~~~java
Comparator<String> byLength =
    (left, right) -> Integer.compare(left.length(), right.length());
~~~

cũng hợp lệ và có cùng ý nghĩa thứ tự độ dài, nhưng dài hơn và khiến người đọc phải xác nhận hai vế được so sánh đúng. Trong trường hợp này, phương thức thư viện `comparingInt` làm ý định nổi bật hơn.

**Đừng hiểu “method reference luôn tốt”**: nếu có quy tắc đặc thù, ví dụ phải xử lý độ dài tối đa hoặc phân biệt chuỗi null, lambda có thể là lựa chọn đúng. Đánh giá cả **phương thức ngoài** (map/filter/sorted/forEach) lẫn **phương thức được tham chiếu**.

## 4. Lambda: để quy tắc nghiệp vụ nằm ngay chỗ sử dụng

Dạng lambda rõ hơn khi quyết định được thể hiện bằng biểu thức hoặc block:

~~~java
Predicate<String> validEmail = email ->
        email != null
        && !email.isBlank()
        && email.contains("@");
~~~

Đây chỉ là **ví dụ điều kiện đơn giản để học cú pháp**, không phải thuật toán xác thực email đầy đủ. Nó cho thấy yêu cầu “không null, không blank, có dấu @” ngay tại callback. Thay bằng `String::contains` không biểu diễn đủ điều kiện và cũng không cung cấp sẵn chuỗi tìm kiếm.

Ví dụ với nhiều bước:

~~~java
Function<String, String> displayName = name -> {
    if (name == null || name.isBlank()) {
        return "(unknown)";
    }
    String cleaned = name.strip();
    return cleaned.substring(0, 1).toUpperCase(Locale.ROOT)
            + cleaned.substring(1);
};
~~~

Đoạn mã minh họa trong một phương thức, cần import `java.util.Locale`, `java.util.function.Function`. `String.isBlank/strip` là API **Java 11+**. Người đọc thấy rõ:
- Cách ứng xử với đầu vào null/rỗng.
- Bước xóa khoảng trắng.
- Quy tắc chỉ viết hoa ký tự đầu theo code-unit của ví dụ.

Đoạn này **không phải hàm chuẩn hóa tên đa ngôn ngữ hoàn chỉnh** (ví dụ chữ cái có nhiều code point hay quy tắc locale đặc biệt); nếu triển khai cho tên quốc tế, hãy thiết kế Unicode/case mapping đầy đủ. Ý ở đây là: khi cần diễn tả nhiều quy tắc, một lambda có tên rõ ràng tốt hơn việc ghép nhiều method references thiếu ngữ cảnh.

### Khi logic dài hơn một vài dòng

Nếu callback ngày càng dài hoặc được dùng ở nhiều nơi, hãy **tách thành phương thức có tên theo nghiệp vụ**, rồi cân nhắc method reference:

~~~java
private static boolean canNotify(User user) {
    return user.points() >= 50
            && user.email() != null
            && !user.email().isBlank();
}

// Trong pipeline:
users.stream()
     .filter(IntentReadableDemo::canNotify);
~~~

`canNotify` không chỉ “kiểm tra” mà nói rõ **ý định nghiệp vụ của bộ lọc**. So với việc lặp lại điều kiện ở ba pipeline khác nhau, method reference tới helper đặt tên tốt dễ bảo trì hơn. Nhưng không nên tạo hàng loạt helper với tên vô nghĩa như `process` hoặc `handle` chỉ để biến mọi lambda thành reference.

Tư duy phù hợp:
- Nếu hành vi **đơn giản và đã có tên rõ**: dùng method reference.
- Nếu **đơn giản nhưng quy tắc thể hiện rõ hơn bằng biểu thức**: dùng lambda.
- Nếu **nhiều bước/được dùng lại**: tạo phương thức có tên nghiệp vụ, rồi dùng reference nếu giúp dễ đọc.

## 5. Tên hàm và vị trí trong pipeline phải nói lên mục đích

So sánh hai pipeline:

~~~java
List<String> recipients = users.stream()
    .filter(u -> u.points() >= 50
                 && u.email() != null
                 && !u.email().isBlank())
    .map(u -> u.email())
    .map(s -> s.strip().toLowerCase(Locale.ROOT))
    .sorted()
    .toList();
~~~

và:

~~~java
List<String> recipients = users.stream()
    .filter(IntentReadableDemo::canNotify)
    .map(User::email)
    .map(IntentReadableDemo::normalizeEmail)
    .sorted()
    .toList();
~~~

Đây là các đoạn minh họa trong ngữ cảnh có `User`, `users` và hai helper. Pipeline thứ hai cho thấy các bước rõ ở mức ý định: **chọn người có thể thông báo → lấy email → chuẩn hóa → sắp xếp → lấy danh sách**. Khi muốn biết chính sách “có thể thông báo” hay “chuẩn hóa”, người đọc tìm đến phương thức có tên.

Tuy nhiên, cách thứ hai **không mặc nhiên tốt hơn** nếu helper ở rất xa hoặc tên không đáng tin. Nếu chỉ có một điều kiện cực ngắn, lambda ngay tại chỗ đôi khi dễ đọc hơn; điều quan trọng là **mức trừu tượng nhất quán** trong pipeline. Đừng trộn một reference có ý nghĩa nghiệp vụ với các lambda nhiều dòng đầy chi tiết kỹ thuật mà không có lý do.

### Tên cho các bước có side effect

~~~java
Consumer<String> notifyUser = address ->
        notificationGateway.send(address);
recipients.forEach(notifyUser);
~~~

Đây là **mã minh họa phụ thuộc `notificationGateway` của ứng dụng**, không phải chương trình độc lập. Tên `notifyUser` giúp phân biệt hành động gửi thông báo với việc chỉ chuyển đổi địa chỉ. Nếu `notificationGateway::send` thể hiện rõ đối tượng và ý nghĩa hơn, bạn có thể dùng reference trực tiếp; nếu callback cần bổ sung audit/idempotency policy, lambda hoặc method nghiệp vụ đặt tên rõ sẽ phù hợp hơn.

Đừng dùng `forEach` để giả vờ rằng pipeline đang tạo giá trị mới; `forEach` là terminal operation trả `void`, còn `map` trả Stream với các phần tử biến đổi.

## 6. Ranh giới rất quan trọng: thay đổi hành vi khi refactor

Không phải cứ tìm thấy lambda `x -> obj.method(x)` là được thay cơ học thành `obj::method`. Trước khi thay, kiểm tra **receiver**, **thời điểm đánh giá**, **thứ tự đối số**, **exception**, **null**, và **kiểu trả về**.

### 6.1. Reference bound đánh giá receiver khi tạo

~~~java
Function<String, String> fixed = currentPrefix()::concat;
Function<String, String> dynamic = value -> currentPrefix().concat(value);
~~~

Nếu `currentPrefix()` trả chuỗi `"v1"` khi xây dựng callback, rồi sau đó trả `"v2"`:
- `fixed.apply("!")` dùng receiver **đã chọn lúc tạo** và trả `"v1!"`.
- `dynamic.apply("!")` gọi `currentPrefix()` **tại lúc apply**, trả `"v2!"`.

Trong chương trình chạy ở phần 9, ví dụ này cho stdout `receiver=v1!,v2!`. Chuyển lambda sang reference dù trông gọn có thể làm thay đổi service hoặc trạng thái được nhìn thấy, nhất là khi receiver đến từ factory, dependency injection, request scope hoặc cache.

**Cần phân biệt:** bound reference lưu **đối tượng receiver**, không snapshot toàn bộ trạng thái mutable của object. Nếu receiver là một đối tượng có field thay đổi, phương thức gọi sau đó vẫn có thể nhìn thấy thay đổi bên trong object ấy.

### 6.2. Null receiver không ném lỗi cùng lúc

~~~java
String maybeNull = null;

// NPE ngay khi tạo reference (nếu thực thi):
Supplier<String> broken = maybeNull::trim;

// Tạo lambda được, NPE chỉ khi gọi get():
Supplier<String> deferred = () -> maybeNull.trim();
~~~

Đây là **đoạn ví dụ phân tích lỗi, không chạy như một chương trình bình thường**. Với reference dạng `String::trim` được gán cho `Function<String,String>`, đối tượng String được cung cấp **khi gọi** `apply`, nên `apply(null)` mới dẫn tới NPE.

Chính sách null phải rõ ở API; nếu muốn chuyển null thành chuỗi mặc định, hãy thể hiện rõ trong lambda/helper thay vì dựa vào kiểu viết.

### 6.3. Method reference không tự đảo thứ tự tham số

~~~java
BiFunction<String, String, String> direct = String::concat;
// direct.apply("A", "B") -> "AB"

BiFunction<String, String, String> reversed =
        (left, right) -> right.concat(left);
// reversed.apply("A", "B") -> "BA"
~~~

Tại `String::concat`, đối số đầu tiên của `BiFunction` là **receiver**, đối số thứ hai là tham số `concat`. Nếu mục tiêu là đảo đối số, giữ lambda rõ ràng. Đừng đổi sang reference vì hai bên chỉ khác vài ký tự.

### 6.4. Return/void: “chạy được” chưa chắc đúng ý định

~~~java
List<String> log = new ArrayList<>();

Consumer<String> addToLog = log::add;
Function<String, Boolean> addWithResult = log::add;
~~~

Hai lời gọi đều thêm phần tử vào `log`. `List.add` trả `boolean`, nhưng với `Consumer.accept` kết quả bị bỏ. Khi kết quả báo thành công là thứ nghiệp vụ cần, `Function` hoặc API trả trạng thái rõ ràng mới đúng. **Không thể kết luận chỉ dựa trên cú pháp `::`** rằng hành động có hay không có side effect hoặc có giá trị trả về.

Đoạn sau dễ gây lỗi logic:

~~~java
Consumer<String> wasted = String::trim;
~~~

Nó có thể **biên dịch** vì lời gọi `trim` trả giá trị String nhưng target `Consumer` cho phép bỏ kết quả. Nó không sửa chuỗi gốc vì `String` bất biến. Nếu muốn danh sách đã trim, cần `Function` cho `map`.

## 7. Biết khi nào cần bảo vệ sự rõ ràng trước cú pháp “ngắn”

### 7.1. Overload làm ý định mờ

Một method reference có thể cần compiler chọn giữa các overload theo chữ ký của functional interface đích. Với:

~~~java
Function<String, Integer> boxed = Integer::parseInt;
ToIntFunction<String> primitive = Integer::parseInt;
~~~

Cùng tham chiếu `Integer::parseInt` nhưng target function type khác nhau. Kết quả `boxed.apply("7")` là `Integer` (qua boxing), còn `primitive.applyAsInt("7")` là `int`. Dù có thể cùng giá trị số học, hai hợp đồng không hoàn toàn như nhau về kiểu.

Khi hàm overload nhận nhiều callback, nếu ý định khó thấy hoặc compiler báo ambiguous, có thể tách biến có functional type tường minh trước khi truyền:

~~~java
Function<String, Integer> parseNumber = Integer::parseInt;
// report(parseNumber);  // Dùng khi phương thức report nhận Function phù hợp.
~~~

Dòng `report` là **minh họa phụ thuộc API ứng dụng**. Đừng chèn một cast vô nghĩa chỉ để “làm code chạy”; xác định đúng SAM type và ý nghĩa.

### 7.2. Checked exception vẫn phải tương thích với SAM

Giả sử phương thức đọc file khai báo `throws IOException`. `Function<Path,String>.apply` không khai báo checked exception; một method reference trỏ thẳng vào phương thức đó có thể không hợp lệ. Lambda cho phép xử lý lỗi tường minh:

~~~java
Function<Path, String> loadText = path -> {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};
~~~

Đây là **đoạn minh họa bên trong phương thức**, cần import `java.nio.file.*`, `java.io.*`, `java.util.function.*`. `Files.readString` có từ Java 11. Chuyển thành unchecked exception là một **quyết định về hợp đồng lỗi**, không phải quy tắc áp dụng mặc định cho mọi hệ thống; API khác có thể cần xử lý lỗi theo Result type hoặc interface với `throws`.

### 7.3. Nhất quán quan trọng hơn “100% method reference”

~~~java
users.stream()
    .filter(IntentReadableDemo::canNotify)
    .map(User::email)
    .map(email -> email.strip().toLowerCase(Locale.ROOT))
    .forEach(System.out::println);
~~~

Kết hợp reference cho hành vi có tên sẵn và lambda cho thao tác kết hợp là **hoàn toàn hợp lý**. Ép tất cả thành reference bằng cách tạo helper `stripAndLower` không có ý nghĩa nghiệp vụ riêng đôi khi tăng số chỗ cần truy cập mà không làm code dễ hiểu hơn.

Nếu bản thân bước chuẩn hóa có nhiều nơi tái sử dụng, đặt tên `normalizeEmail` mới có giá trị.

## 8. Giao diện hàm phải phù hợp với ý định dữ liệu

| Nhu cầu | Functional interface | Kỹ thuật đọc dễ |
| --- | --- | --- |
| Trích thuộc tính từ object | `Function<T,R>` | `User::email` |
| Biến đổi một dữ liệu | `Function<T,R>` hoặc `UnaryOperator<T>` | `String::strip` nếu không có logic bổ sung |
| Kiểm tra điều kiện | `Predicate<T>` | `String::isEmpty` hoặc `x -> x != null && ...` |
| So sánh theo khóa nguyên thủy | `ToIntFunction<T>` trong `Comparator.comparingInt` | `Comparator.comparingInt(User::points)` |
| Tạo object | `Supplier<T>` hoặc `Function<A,T>` | `ArrayList::new`, `User::new` nếu constructor phù hợp |
| Nhận dữ liệu để tạo side effect | `Consumer<T>` | `System.out::println`, `auditLog::add` |
| Nhận hai dữ liệu để tạo side effect | `BiConsumer<T,U>` | Lambda với hai tham số hoặc method reference phù hợp |
| Chạy một hành động không có tham số | `Runnable` | `task::run` hoặc `() -> ...` |
| Lấy một giá trị theo yêu cầu | `Supplier<T>` | `service::get` nếu receiver cố định hợp lý |

Để chọn đúng hình thức, nhìn **ý định của API tiếp nhận callback**: `Stream.map` cho dữ liệu mới; `Stream.filter` cho điều kiện; `Stream.forEach` cho side effect; `Optional.map` biến đổi giá trị; `Optional.ifPresent` thực hiện hành động với giá trị nếu có; `CompletableFuture.thenApply` chuyển đổi kết quả, còn `thenAccept` nhận kết quả và thực thi `Consumer`.

### Tránh side effect ẩn trong phép biến đổi

~~~java
// Không khuyến nghị: đưa side effect vào map chỉ để tiện viết callback.
List<String> collected = new ArrayList<>();
users.stream()
     .map(user -> {
         collected.add(user.email());
         return user.email();
     })
     .toList();
~~~

Đây là **đoạn anti-pattern minh họa**. Nếu muốn lấy email, dùng `.map(User::email).toList()` và tiêu thụ danh sách trả về. Nếu cần ghi log thật sự, bố trí một bước có chủ ý; `peek` chủ yếu phục vụ quan sát/debug và không nên mang các side effect nghiệp vụ bắt buộc vì Stream có thể tối ưu hóa hoặc short-circuit.

Trong Stream song song, `forEach` không bảo đảm encounter order và callback có thể chạy đa luồng; reference `auditLog::add` không tự biến `ArrayList` thành thread-safe. **Lựa chọn kiểu viết giúp người đọc nhận ra ý định, nhưng không tự giải quyết concurrency.**

## 9. Chương trình Java 17+ minh họa cách chọn cho người đọc

Tình huống: danh sách người dùng có email và điểm. Chỉ những người thỏa điều kiện mới được thông báo, email phải được chuẩn hóa; cần ghi audit, xếp hạng theo điểm và trình bày một số nhãn trạng thái. Ví dụ cố ý phối hợp **method reference ở bước đơn** và **lambda ở bước nhiều logic**.

Lưu thành **IntentReadableDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class IntentReadableDemo {
    static final class User {
        private final String email;
        private final int points;
        User(String email, int points) {
            this.email = email;
            this.points = points;
        }
        String email() { return email; }
        int points() { return points; }
    }

    private static String prefix = "v1";

    private static String currentPrefix() { return prefix; }

    private static boolean canNotify(User user) {
        return user.points() >= 50
                && user.email() != null
                && !user.email().isBlank();
    }

    private static String normalizeEmail(String raw) {
        return raw.strip().toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<User> users = List.of(
                new User(" LINH@EXAMPLE.COM ", 72),
                new User(" ", 95),
                new User("Mai@Example.com", 43),
                new User(" an@example.com ", 65)
        );

        List<String> recipients = users.stream()
                .filter(IntentReadableDemo::canNotify)
                .map(User::email)
                .map(IntentReadableDemo::normalizeEmail)
                .sorted()
                .toList();

        System.out.println("recipients=" + recipients);

        Consumer<String> notify = address ->
                System.out.println("notify=" + address);
        recipients.forEach(notify);

        List<String> auditLog = new ArrayList<>();
        recipients.forEach(auditLog::add);
        System.out.println("audit=" + auditLog);

        List<String> rank = users.stream()
                .filter(IntentReadableDemo::canNotify)
                .sorted(Comparator.comparingInt(User::points).reversed())
                .map(user -> normalizeEmail(user.email()) + "=" + user.points())
                .toList();
        System.out.println("ranking=" + rank);

        List<String> labels = List.of(" new ", "  ", "active")
                .stream()
                .map(String::strip)
                .filter(Predicate.not(String::isEmpty))
                .map(value -> "status:" + value)
                .toList();
        System.out.println("labels=" + labels);

        Function<String, String> fixed = currentPrefix()::concat;
        Function<String, String> dynamic = value -> currentPrefix().concat(value);
        prefix = "v2";
        System.out.println("receiver=" + fixed.apply("!") + "," + dynamic.apply("!"));

        users.stream()
                .filter(IntentReadableDemo::canNotify)
                .findFirst()
                .ifPresent(user -> System.out.println(
                        "first=" + normalizeEmail(user.email())));
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 IntentReadableDemo.java
java IntentReadableDemo
~~~

Stdout chính xác đã xác minh bằng biên dịch và chạy:

~~~text
recipients=[an@example.com, linh@example.com]
notify=an@example.com
notify=linh@example.com
audit=[an@example.com, linh@example.com]
ranking=[linh@example.com=72, an@example.com=65]
labels=[status:new, status:active]
receiver=v1!,v2!
first=linh@example.com
~~~

### Giải thích từng lựa chọn

1. **`filter(IntentReadableDemo::canNotify)`:** người đọc thấy “lọc người có thể thông báo”, không bị phân tán bởi ba điều kiện kỹ thuật. Helper có tên nghiệp vụ, đủ đáng để tham chiếu.
2. **`map(User::email)`:** một phép lấy thuộc tính trực tiếp, không cần tên tham số chỉ để gọi lại accessor.
3. **`map(IntentReadableDemo::normalizeEmail)`:** biến đổi nhiều bước nhưng đã có helper tên rõ nghĩa và có thể dùng lại. `Locale.ROOT` làm phép lower-case không phụ thuộc locale hệ thống; đối với email thực tế, chính sách case normalization cần tuân theo quy tắc địa chỉ của hệ thống, không suy luận rằng mọi phần local của email đều tương đương không phân biệt hoa thường.
4. **`sorted()` và `toList()`:** phương thức thư viện đã biểu đạt ý định. `Stream.toList()` có từ Java 16 và tạo danh sách không sửa được; không cần tự đưa vào `forEach` để gom dữ liệu.
5. **`Consumer<String> notify = address -> ...`:** lambda ngắn diễn tả rõ side effect hiển thị mô phỏng thông báo. Biến `notify` đặt tên theo hành động giúp dễ phân biệt với phép biến đổi dữ liệu.
6. **`auditLog::add`:** một method reference bound tới danh sách cụ thể diễn tả việc thêm audit. `List.add` trả boolean, nhưng `Consumer` của `forEach` bỏ kết quả đó. Ví dụ chỉ chạy tuần tự; không dùng y nguyên với parallel stream và ArrayList chia sẻ.
7. **`Comparator.comparingInt(User::points).reversed()`:** API comparator + accessor rõ ý định “xếp theo điểm giảm dần”, tránh tự viết biểu thức trừ điểm có nguy cơ overflow.
8. **`map(user -> normalizeEmail(user.email()) + "=" + user.points())`:** lambda rõ hơn vì ghép hai dữ liệu và định dạng nhãn kết quả. Một reference đơn không nói được quy tắc định dạng đó.
9. **`map(String::strip).filter(Predicate.not(String::isEmpty))`:** tên method thể hiện xóa khoảng trắng và loại chuỗi rỗng. `String.strip` và `Predicate.not` có từ Java 11; input demo không có null. Với dữ liệu có null, cần xử lý trước.
10. **`fixed` so với `dynamic`:** ví dụ chứng minh thay dạng viết có thể đổi **thời điểm chọn receiver**. Reference giữ `"v1"`, lambda thấy `"v2"`.
11. **`ifPresent(user -> ...)`:** lambda được chọn vì phải lấy email, chuẩn hóa rồi in. Nếu chỉ cần in nguyên object hoặc một chuỗi đã có, method reference trực tiếp có thể phù hợp hơn.

Đầu ra của ví dụ giữ thứ tự nhờ dữ liệu nguồn là `List`, pipeline tuần tự và phép `sorted()`. Đừng suy luận từ chương trình rằng mọi `HashSet` hay `parallelStream().forEach` sẽ có cùng thứ tự quan sát.

## 10. Dùng độ dài và mức trừu tượng hợp lý

Có ba cấp đọc code:

**Cấp 1 — tại nơi gọi:** nên cho biết tiến trình nghiệp vụ, chẳng hạn `filter(canNotify) -> map(email) -> map(normalizeEmail)`.

**Cấp 2 — helper:** chứa quy tắc cụ thể như kiểm tra điểm, null, chuẩn hóa chuỗi. Tên helper phải chính xác và bền với thay đổi yêu cầu.

**Cấp 3 — API chuẩn:** các phương thức quen thuộc như `String::strip`, `Integer::parseInt`, `Comparator.comparingInt` hoặc `Collectors.toMap` đã mang thông điệp đủ rõ; không cần đặt lại tên mỗi thao tác trừ khi chính sách nghiệp vụ khác mặc định.

Một số dấu hiệu của **refactor tốt**:

- Loại bỏ những lambda chỉ chuyển lời gọi `x -> x.method()` mà không đổi hành vi.
- Đặt tên điều kiện dài theo ý nghĩa nghiệp vụ, không theo cấu trúc cú pháp (`canNotify` thay cho `checkUser`).
- Giữ lambda khi nó nói rõ null handling, fallback, exception policy hoặc thứ tự khác.
- Dùng helper khi tái sử dụng hoặc khi pipeline đang trộn quá nhiều mức trừu tượng.
- Không thêm helper chỉ để làm code trông “thuần method reference”.
- Có test bảo vệ kết quả, ngoại lệ và side effect trước khi chuyển đổi cú pháp, nhất là bound receiver.

### Có nên chuẩn hóa toàn bộ codebase chỉ một kiểu viết?

Không. Một quy tắc “bắt buộc mọi lambda một dòng chuyển thành method reference” dễ làm mất thông tin quan trọng trong ngữ cảnh có overload, receiver động hoặc điều kiện nghiệp vụ. Ngược lại, cấm mọi method reference khiến code lặp `x -> x.getValue()` mà không cung cấp thêm ý nghĩa.

Tính nhất quán nên nằm ở **mục đích và nguyên tắc**: callback chỉ gọi phương thức sẵn có thì cân nhắc reference; callback có logic thì dùng lambda; luôn kiểm tra lại semantics.

## 11. Version notes: diễn đạt hiện đại nhưng không bỏ quên target JDK

Các đặc tính **lambda**, **method reference**, `java.util.function`, `Stream.map/filter/forEach` và `Comparator.comparingInt` xuất hiện từ Java 8 và vẫn được sử dụng.

| API trong ví dụ | JDK tối thiểu | Ghi chú dùng hiện nay |
| --- | --- | --- |
| `String.trim` | Có trước Java 8 | Xử lý tập ký tự khoảng trắng theo quy tắc riêng; không giống hoàn toàn `strip` |
| `String.strip` / `isBlank` | Java 11 | Xử lý khoảng trắng theo quy tắc Unicode `Character.isWhitespace` |
| `Predicate.not` | Java 11 | Cho phép viết `Predicate.not(String::isEmpty)` dễ đọc |
| `List.of` | Java 9 | Tạo list không sửa được, từ chối phần tử null |
| `Stream.toList` | Java 16 | Kết quả không sửa được; không coi là giống mọi `Collectors.toList` về hợp đồng |
| `Locale.ROOT` | Có từ trước Java 8 | Hữu ích khi cần case mapping độc lập locale mặc định |
| `Comparator.comparingInt` | Java 8 | So sánh khóa `int`, không cần tự viết phép trừ |
| `String[]::new` | Java 8 (method reference) | Tham chiếu constructor của mảng |

Nếu dự án bị khóa ở Java 8, thay `Stream.toList()` bằng `collect(Collectors.toList())` (nhưng **không** giả định collector này cam kết khả năng sửa được; khi cần một list sửa được cụ thể, dùng `Collectors.toCollection(ArrayList::new)`). Thay `String.strip/isBlank` hoặc `Predicate.not` bằng cách hiện hành tương thích với JDK đích và chính sách whitespace của ứng dụng.

Việc ưu tiên kiến thức hiện hành không có nghĩa phải tránh các API của Java 8: những API đó vẫn là nền tảng cho cách viết Java ngày nay. Chỉ cần ghi rõ khi dùng API được bổ sung ở phiên bản mới hơn.

## 12. Những sai lầm thường gặp

| Cách viết hoặc nhận định | Vấn đề | Cách chọn đúng |
| --- | --- | --- |
| “Method reference ngắn hơn nên chắc chắn dễ đọc hơn” | Cú pháp ngắn có thể che receiver/overload | So sánh khả năng hiểu ý định và semantics |
| Thay `x -> x != null && x.isBlank()` bằng `String::isBlank` | Mất kiểm tra null | Giữ lambda hoặc helper chính xác |
| Thay `x -> currentService().send(x)` bằng `currentService()::send` | Receiver bị chọn sớm | Giữ lambda nếu phải chọn service mỗi invocation |
| Đổi `(a,b) -> b.concat(a)` thành `String::concat` | Đảo chiều nối chuỗi | Giữ lambda |
| `Consumer<String> callback = String::trim;` để chuẩn hóa dữ liệu | Kết quả bị bỏ, không đổi String gốc | Dùng `Function` với `map` |
| Lạm dụng `forEach(log::add)` để tạo list mới | Side effect không cần thiết và có thể nguy hiểm khi song song | Dùng `map(...).toList()` hoặc collector |
| Đặt helper tên `process`, `handle` cho mọi lambda | Tên không biểu đạt nghiệp vụ | Dùng tên như `canNotify`/`normalizeEmail` |
| Đưa logic bắt buộc vào `Stream.peek` | Pipeline có thể bỏ qua callback trong một số tối ưu hóa | Tách xử lý bắt buộc thành bước rõ ràng |
| Xem `list::add` như hành động thread-safe | Method reference không tạo synchronization | Kiểm soát thread safety khi có concurrency |
| Nghĩ `::` tự quyết định kiểu hàm | Method reference cần target SAM như lambda | Xác định `Function`/`Consumer`/`Predicate`... |
| Mọi reference đều được gọi ngay khi tạo | Bound receiver expression đánh giá ngay, **target method** chưa chắc được gọi | Phân biệt chọn receiver với thực thi callback |
| Chọn kiểu viết theo hiệu năng đoán trước | Không có quy tắc method reference luôn nhanh hơn | Ưu tiên rõ ràng; benchmark khi có nhu cầu thực |
| `var f = String::trim;` | Không đủ target type cho poly expression | Khai báo `Function<String,String> f = String::trim;` |
| Ép callback ném checked exception vào `Function` | SAM không cho throws tương ứng | Dùng adapter lambda xử lý lỗi hoặc interface phù hợp |
| Dùng `toList()` và mặc định được `add` | `Stream.toList` trả list không sửa được | Chọn collector trả collection phù hợp |

## 13. Bài tập luyện tư duy về ý định

1. Với `List<String>` không có null, hãy viết hai pipeline chuyển chuỗi thành độ dài bằng lambda và method reference. Vì sao `String::length` là lựa chọn rõ?
2. Với chuỗi có thể null, hãy thiết kế quy tắc “null -> chuỗi rỗng; khác null -> strip” và giải thích tại sao `String::strip` trực tiếp không đủ.
3. Vì sao `Comparator.comparingInt(User::points)` thường dễ đọc và an toàn hơn `(a,b) -> a.points() - b.points()`?
4. Giả sử một API trả `Service` khác nhau theo request. So sánh thời điểm chọn service trong `getService()::execute` và `() -> getService().execute()`.
5. Một lambda ghép `user.email() + ":" + user.points()` có nên đổi thành `User::email` không? Điều gì mất đi?
6. Hãy tạo helper `canNotify(User)` từ một điều kiện gồm điểm tối thiểu, null và blank email. Vì sao việc đặt tên có thể cải thiện pipeline?
7. `list::add` hợp lệ với `Consumer<T>` dù `add` trả boolean. Khi nào bạn cần chọn `Function<T,Boolean>` để không bỏ mất thông tin?
8. Một `Stream` dùng `map(x -> { audit.add(x); return transform(x); })`. Bạn sẽ tách phần side effect thế nào để code thể hiện rõ ý định, nhất là nếu sau này chạy song song?
9. Hãy viết comparator sắp xếp theo điểm giảm dần. So sánh độ rõ của `Comparator.comparingInt(User::points).reversed()` và lambda so sánh trực tiếp.
10. Với một method reference bị compiler báo ambiguous overload, cần xem các thông tin target typing nào? Khi nào khai báo `Function` trung gian giúp dễ đọc?
11. Viết pipeline chuẩn hóa email bằng `map(String::strip)`, `map(String::toLowerCase)` và một lambda có `Locale.ROOT`. Cách nào đúng chính sách locale của dự án hơn? (Lưu ý `String::toLowerCase` không tự truyền `Locale.ROOT`.)
12. Chỉ ra một ví dụ **có thể** đổi lambda sang reference mà không thay hành vi, và một ví dụ **không thể** đổi an toàn vì receiver expression có side effect.

## Tài liệu API và đặc tả chính thức

- [Java Language Specification – Method Reference Expressions, `15.13](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13)
- [Java Language Specification – Lambda Expressions, `15.27](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27)
- [Java SE 17 – java.util.function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java SE 17 – Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 17 – Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Java SE 17 – String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)

**Kết luận:** Hãy chọn **method reference** khi tên phương thức hiện có truyền đạt đúng một hành động và ánh xạ tham số trực tiếp. Hãy chọn **lambda** khi cần làm rõ điều kiện, thứ tự, null, biến đổi bổ sung hoặc ngoại lệ. Với logic nghiệp vụ đủ quan trọng, đặt tên phương thức rồi tham chiếu đến nó. **Sự rõ ràng của ý định và việc giữ nguyên semantics luôn quan trọng hơn việc tiết kiệm vài ký tự.**
