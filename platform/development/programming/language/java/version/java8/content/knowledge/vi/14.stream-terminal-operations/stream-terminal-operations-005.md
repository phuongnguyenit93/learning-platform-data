# Stream.findFirst(), Stream.findAny() và kết quả có thể vắng mặt

**Chủ đề:** Java 8 → Kết thúc Stream. Hai phương thức **findFirst()** và **findAny()** xuất hiện từ Java 8, vẫn được sử dụng trong Java hiện đại. Ví dụ chạy độc lập bên dưới dùng Java 17+ để tận dụng cú pháp và tiện ích hiện hành.

## 1. Kết quả học tập

Sau bài này, bạn có thể:
- Phân biệt phần tử **đầu tiên theo encounter order** với **một phần tử bất kỳ**.
- Dự đoán đúng kết quả của stream có thứ tự, không có thứ tự, stream rỗng và stream song song.
- Xử lý **Optional<T>** khi không tìm thấy phần tử, không dựa vào giá trị null hoặc gọi **get()** thiếu kiểm tra.
- Chọn cách tìm phù hợp với yêu cầu nghiệp vụ, tính xác định và chi phí xử lý.

## 2. Tìm một phần tử là thao tác kết thúc Stream

Một pipeline thường có dạng:

~~~java
Optional<String> result = names.stream()
        .filter(name -> name.startsWith("B"))
        .findFirst();
~~~

**stream()** tạo luồng từ nguồn; **filter(...)** giữ phần tử thỏa điều kiện; **findFirst()** là **terminal operation**: kích hoạt xử lý pipeline và trả về kết quả. **findAny()** cũng là terminal operation. Cả hai có chữ ký khái quát:

~~~java
Optional<T> findFirst();
Optional<T> findAny();
~~~

Đây là các thao tác **short-circuiting**: có thể kết thúc trước khi duyệt hết nguồn khi đủ điều kiện tìm được một phần tử. Tuy nhiên, short-circuit không bảo đảm chỉ một phần tử được xử lý, nhất là trong pipeline song song hoặc có thao tác trung gian phải xử lý nhiều phần tử (ví dụ **sorted()**).

Một Stream đã chạy terminal operation thì đã được tiêu thụ: muốn tìm lần nữa phải tạo Stream mới từ nguồn. Không gọi **findFirst()** rồi **findAny()** trên cùng một đối tượng Stream.

## 3. findFirst() và findAny() khác nhau ở đâu?

| Khía cạnh | **findFirst()** | **findAny()** |
|---|---|---|
| Phần tử được chọn | Phần tử đầu tiên **theo encounter order**, nếu stream có thứ tự | Một phần tử bất kỳ; không cam kết là phần tử đầu |
| Stream không có encounter order | Có thể chọn bất kỳ phần tử nào | Có thể chọn bất kỳ phần tử nào |
| Stream song song có thứ tự | Vẫn phải bảo toàn phần tử đầu theo encounter order | Có quyền chọn phần tử sẵn có từ nhánh xử lý bất kỳ |
| Tính xác định | Xác định nếu thứ tự nguồn/pipeline xác định | Được đặc tả là **nondeterministic**, kể cả khi thường quan sát thấy cùng kết quả |
| Kiểu trả về | **Optional<T>** | **Optional<T>** |
| Không có phần tử | **Optional.empty()** | **Optional.empty()** |

**Encounter order** là thứ tự phần tử mà nguồn/pipeline quy định. Ví dụ, stream từ **List.of("An", "Bình", "Bảo")** giữ thứ tự danh sách. Sau khi lọc tên bắt đầu bằng B, **findFirst()** trả về "Bình". Stream lấy từ cấu trúc không bảo đảm thứ tự như **HashSet** không có thứ tự đầu tiên mà nghiệp vụ được phép dựa vào.

~~~java
List<String> names = List.of("An", "Bình", "Bảo");

String first = names.stream()
        .filter(name -> name.startsWith("B"))
        .findFirst()
        .orElse("Không thấy"); // "Bình", vì List có encounter order

Optional<String> any = names.parallelStream()
        .filter(name -> name.startsWith("B"))
        .findAny(); // có thể chứa "Bình" hoặc "Bảo"
~~~

**Không kết luận rằng findAny() luôn chọn ngẫu nhiên, luôn chọn phần tử đầu trên stream tuần tự hoặc chắc chắn nhanh hơn.** Đặc tả chỉ cho phép nó chọn bất kỳ phần tử phù hợp nào. Nếu không cần phần tử cụ thể, quyền tự do này *có thể* giúp tối ưu hóa thực thi song song; hiệu năng thật còn phụ thuộc dữ liệu, pipeline và chi phí điều phối luồng.

Gọi **unordered()** có thể bỏ ràng buộc encounter order, nhưng **không xáo trộn dữ liệu**. Sau khi bỏ ràng buộc, ngay cả **findFirst()** cũng không còn bảo đảm phần tử đầu như trước.

## 4. Ví dụ đầy đủ, chạy được trên Java 17+

Lưu nội dung sau thành **FindExamples.java**:

~~~java
import java.util.List;
import java.util.Optional;

public class FindExamples {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi", "Bảo");

        Optional<String> firstB = names.stream()
                .filter(name -> name.startsWith("B"))
                .findFirst();
        System.out.println(firstB.orElse("Không tìm thấy"));

        Optional<String> missing = names.stream()
                .filter(name -> name.startsWith("Z"))
                .findAny();
        System.out.println(missing.isEmpty());
        System.out.println(missing.orElse("Chưa có kết quả"));

        Optional<String> anyB = names.parallelStream()
                .filter(name -> name.startsWith("B"))
                .findAny();
        System.out.println(anyB.isPresent());

        Optional<String> firstBParallel = names.parallelStream()
                .filter(name -> name.startsWith("B"))
                .findFirst();
        System.out.println(firstBParallel.orElse("Không tìm thấy"));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 FindExamples.java
java FindExamples
~~~

**Stdout chính xác:**

~~~text
Bình
true
Chưa có kết quả
true
Bình
~~~

Giải thích:
1. Nguồn là **List** có encounter order; phần tử đầu thỏa chữ B là "Bình".
2. Không có tên bắt đầu bằng Z nên **findAny()** trả **Optional.empty()**; **isEmpty()** là **true** và **orElse(...)** dùng giá trị dự phòng.
3. Với **findAny()** song song, không in tên được chọn vì tên đó không được đặc tả; chỉ in **isPresent()**, luôn **true** vì có hai tên phù hợp và không có lỗi.
4. **findFirst()** song song vẫn trả "Bình" vì danh sách có thứ tự.

**Ghi chú phiên bản:** **findFirst()**, **findAny()**, **Optional.isPresent()** và **Optional.orElse()** có từ Java 8. **List.of(...)** xuất hiện từ Java 9; **Optional.isEmpty()** từ Java 11. Ví dụ sử dụng Java 17+ như đã công bố, không giả định các tiện ích mới tồn tại trên JDK 8.

## 5. Optional<T>: một kết quả có thể có hoặc không

Khi tìm thấy một phần tử không-null, kết quả là một **Optional** có chứa giá trị. Khi không có phần tử sau khi lọc, kết quả là **Optional.empty()**; bản thân đối tượng Optional mà API trả về **không phải null**.

~~~text
Stream nguồn → filter (nếu có) → findFirst/findAny
                                  ├─ Có phần tử → Optional chứa giá trị
                                  └─ Không có    → Optional.empty()
~~~

Đây là cách biểu diễn tình huống "không tìm thấy" bằng kiểu dữ liệu rõ ràng, thay cho việc giả định luôn tồn tại phần tử.

### Các cách xử lý thông dụng

| Cần làm gì? | Cách dùng | Hành vi khi Optional rỗng |
|---|---|---|
| Kiểm tra có kết quả | **isPresent()** | Trả **false** |
| Kiểm tra không có kết quả (Java 11+) | **isEmpty()** | Trả **true** |
| Thực thi khi có giá trị | **ifPresent(consumer)** | Không thực thi consumer |
| Xử lý đủ hai nhánh (Java 9+) | **ifPresentOrElse(consumer, runnable)** | Thực thi runnable |
| Lấy giá trị dự phòng cố định | **orElse(defaultValue)** | Trả defaultValue |
| Tạo giá trị dự phòng khi cần | **orElseGet(supplier)** | Gọi supplier và trả kết quả |
| Buộc phải có giá trị | **orElseThrow(...)** | Ném ngoại lệ |
| Biến đổi giá trị nếu tồn tại | **map(mapper)** | Giữ Optional rỗng |

Các đoạn sau là **đoạn minh họa**, giả sử biến **result** có kiểu **Optional<String>** được tạo trước:

~~~java
String displayName = result.orElse("Khách");

result.ifPresent(name -> System.out.println("Tìm thấy: " + name));

result.ifPresentOrElse(
        name -> System.out.println("Tìm thấy: " + name),
        () -> System.out.println("Không có kết quả")
);

String requiredName = result.orElseThrow(
        () -> new IllegalArgumentException("Không có tên phù hợp")
);

Optional<Integer> nameLength = result.map(String::length);
~~~

**orElse(...) so với orElseGet(...):** Biểu thức đối số của **orElse(expensiveFallback())** được Java đánh giá trước khi gọi phương thức, kể cả khi Optional đã có giá trị. Với **orElseGet(() -> expensiveFallback())**, hàm dự phòng chỉ được gọi khi Optional rỗng. Nếu dự phòng cần truy vấn dữ liệu, tính toán tốn kém hoặc có tác dụng phụ, nên cân nhắc **orElseGet**.

**Không gọi get() theo thói quen:** **Optional.get()** ném **NoSuchElementException** nếu rỗng. Chỉ dùng khi đã chứng minh có giá trị; thông thường **orElse**, **orElseGet**, **ifPresent** hoặc **orElseThrow** với thông điệp nghiệp vụ giúp ý định rõ hơn. **orElseThrow()** không tham số cũng ném **NoSuchElementException** khi rỗng.

**Không biến Optional trở lại thành null theo mặc định:** Dùng **orElse(null)** có thể tái tạo vấn đề null ở phía gọi; ưu tiên giữ Optional hoặc chọn chính sách xử lý thiếu dữ liệu rõ ràng.

## 6. Chọn thao tác theo tình huống thực tế

### Cần bản ghi đầu tiên theo quy tắc ưu tiên

"Đầu tiên" chỉ có nghĩa nghiệp vụ khi **quy tắc thứ tự được định nghĩa**. Nếu danh sách không sẵn được sắp theo đúng ưu tiên, hãy xác định thứ tự và cả tiêu chí phá hòa trước **findFirst()**.

Ví dụ độc lập Java 17+, lưu thành **PriorityExample.java**:

~~~java
import java.util.Comparator;
import java.util.List;

public class PriorityExample {
    record Task(String id, int priority) {}

    public static void main(String[] args) {
        List<Task> tasks = List.of(
                new Task("T-3", 2),
                new Task("T-2", 3),
                new Task("T-1", 3)
        );

        Task chosen = tasks.stream()
                .filter(task -> task.priority() > 0)
                .sorted(Comparator.comparingInt(Task::priority)
                        .reversed()
                        .thenComparing(Task::id))
                .findFirst()
                .orElseThrow();

        System.out.println(chosen.id());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PriorityExample.java
java PriorityExample
~~~

~~~text
T-1
~~~

Hai task có độ ưu tiên 3 được sắp tiếp theo mã **id** tăng dần, nên kết quả có thể dự đoán. Cách này phù hợp khi yêu cầu chọn **một đối tượng cụ thể** theo thứ tự; lưu ý **sorted()** có thể cần xử lý toàn bộ nguồn nên không mặc nhiên cho lợi ích dừng sớm ở toàn pipeline. **record** dùng ở đây là cú pháp Java hiện đại (Java 16+), không phải điều kiện của **findFirst()**.

### Chỉ cần một phần tử phù hợp, không quan tâm thứ tự

Chọn **findAny()** khi bất kỳ phần tử thỏa điều kiện đều có giá trị sử dụng như nhau. Ví dụ:

~~~java
Optional<String> sample = names.parallelStream()
        .filter(name -> name.startsWith("B"))
        .findAny();
~~~

Nếu chỉ cần trả lời câu hỏi **"có ít nhất một phần tử thỏa điều kiện hay không?"**, dùng **anyMatch(...)** thể hiện ý định trực tiếp hơn:

~~~java
boolean hasNameStartingWithB =
        names.stream().anyMatch(name -> name.startsWith("B"));
~~~

**anyMatch(...)** trả về boolean, không cung cấp phần tử được tìm. **findAny()** trả về Optional của phần tử, cho phép xử lý nội dung nếu có.

### Không có kết quả là tình huống bình thường hay lỗi?

- **Bình thường:** Tìm người dùng theo bộ lọc có thể không có; giữ Optional hoặc hiển thị "Không tìm thấy" bằng **orElse(...)**.
- **Không được phép thiếu:** Quy tắc nghiệp vụ đòi phải có một bản ghi; dùng **orElseThrow(() -> new ...) ** với ngoại lệ có ý nghĩa thay vì tiếp tục với giá trị giả.
- **Phải thử nguồn dự phòng:** Dùng **orElseGet(...)** cho phép tạo giá trị dự phòng theo nhu cầu, hoặc **Optional.or(...)** (Java 9+) nếu muốn giữ dạng Optional.

Không sử dụng một quy tắc dự phòng chung cho mọi API; lựa chọn phụ thuộc ý nghĩa của "không tìm thấy" trong bài toán.

## 7. Các trường hợp góc và lỗi thường gặp

**1. Nguồn trống hoặc filter loại hết dữ liệu.** Hai phương thức đều trả **Optional.empty()**, không ném lỗi chỉ vì không tìm thấy. Nếu pipeline có lỗi khác thì ngoại lệ vẫn có thể xảy ra.

**2. Phần tử được chọn là null.** **findFirst()** và **findAny()** ném **NullPointerException** nếu phần tử được chọn là **null**, vì **Optional** không thể chứa giá trị null. Đừng nhầm trường hợp này với stream rỗng. Với dữ liệu đầu vào có thể null, hãy lọc **Objects::nonNull** trước khi tìm, hoặc dùng **Stream.ofNullable(...)** (Java 9+) nếu bắt đầu từ một phần tử có thể null.

~~~java
Optional<String> safe = java.util.stream.Stream
        .ofNullable((String) null)
        .findFirst();
// safe.isEmpty() == true
~~~

**3. Nhầm encounter order với thứ tự ngẫu nhiên.** **HashSet** không hứa thứ tự duyệt phục vụ nghiệp vụ. Muốn kết quả ổn định theo một tiêu chí, hãy sắp xếp bằng Comparator có tiêu chí phá hòa hợp lý; sau đó dùng **findFirst()**.

**4. Dùng findAny() khi logic cần bản ghi đầu.** Một lần chạy có thể tình cờ trả giá trị mong đợi, nhưng khi chuyển sang **parallelStream()** hoặc đổi cách thực thi, kết quả có thể khác. Không viết kiểm thử khẳng định một phần tử cụ thể từ **findAny()** nếu có nhiều ứng viên hợp lệ.

**5. Coi parallelStream() là cách tăng tốc bắt buộc.** Việc chia việc, đồng bộ và tái kết hợp có chi phí; với tập nhỏ hoặc tác vụ đơn giản, tuần tự có thể tốt hơn. Chỉ tối ưu sau khi đo đúng workload. **findFirst()** trên stream song song có thứ tự đôi khi tốn hơn do phải tôn trọng thứ tự.

**6. Đặt tác dụng phụ trong filter/map/peek để đếm phần tử.** Vì short-circuit và tối ưu hóa pipeline, không nên giả định các hàm này chạy cho mọi phần tử, đúng một lần hoặc theo thứ tự quan sát. Ưu tiên các hàm không phụ thuộc trạng thái thay đổi, đặc biệt khi chạy song song.

**7. Quên rằng Stream chỉ tiêu thụ một lần.** Ví dụ đoạn sau là sai về vòng đời Stream:

~~~java
// Ví dụ lỗi: không chạy cả hai thao tác kết thúc trên cùng Stream
java.util.stream.Stream<String> s = names.stream();
s.findFirst();
s.findAny(); // IllegalStateException vì Stream đã bị tiêu thụ
~~~

Muốn tính nhiều kết quả, tạo stream mới từ **names** hoặc tổ chức lại thuật toán.

## 8. Bài luyện tập có đáp án

Cho danh sách:

~~~java
List<Integer> values = List.of(3, 6, 9, 12);
~~~

1. Với **values.stream().filter(x -> x > 6).findFirst().orElse(-1)**, kết quả là gì?
2. Với **values.stream().filter(x -> x > 20).findAny().isEmpty()**, kết quả là gì?
3. Với **values.parallelStream().filter(x -> x % 3 == 0).findAny()**, có được khẳng định luôn trả 3 không?
4. Nếu yêu cầu "lấy số lớn nhất", nên trực tiếp dùng **findAny()** hay một phép toán biểu đạt giá trị lớn nhất?

**Đáp án và lý do:**
1. **9**, vì 9 là giá trị đầu tiên theo thứ tự List thỏa **x > 6**.
2. **true**, vì không có số nào lớn hơn 20.
3. **Không**; mọi phần tử đều chia hết cho 3, nên thao tác có thể trả bất kỳ phần tử nào trong số đó.
4. Dùng **max(Integer::compareTo)** (trả Optional) hoặc phép tìm cực đại tương đương; **findAny()** không biểu đạt yêu cầu lớn nhất.

## 9. Ghi nhớ khi viết code

- Dùng **findFirst()** nếu cần phần tử đầu theo **thứ tự có nghĩa và được bảo đảm**.
- Dùng **findAny()** nếu bất kỳ kết quả phù hợp nào cũng được chấp nhận; không dựa vào thứ tự hay một hiệu năng bảo đảm.
- Cả hai **có thể trả Optional.empty()**. Xử lý nhánh thiếu dữ liệu rõ ràng bằng API Optional thích hợp.
- Kiểm tra null của nguồn, ý nghĩa của encounter order và vòng đời Stream trước khi dùng trong nghiệp vụ.
- Nếu chỉ cần **boolean**, thường chọn **anyMatch(...)**; nếu cần **giá trị lớn nhất/nhỏ nhất**, chọn **max/min** với Comparator phù hợp.

### Tài liệu API chính thức

- [Stream — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): hợp đồng của **findFirst()**, **findAny()**, **anyMatch()**, short-circuit và hành vi null.
- [Optional — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): **isPresent**, **isEmpty**, **orElse**, **orElseGet**, **orElseThrow**, **map** và các phương thức xử lý kết quả có thể vắng mặt.
