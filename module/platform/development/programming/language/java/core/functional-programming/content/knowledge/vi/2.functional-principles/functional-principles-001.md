# Hàm thuần và điều kiện cùng đầu vào cho cùng đầu ra trong Java

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích **hàm thuần (pure function)** và hai điều kiện phải đồng thời thỏa mãn: kết quả phụ thuộc hoàn toàn vào đầu vào, đồng thời không tạo **tác dụng phụ có thể quan sát được**.
- Phân biệt tính xác định (determinism) với tính thuần, và hiểu ý nghĩa của “cùng đầu vào” khi tham số là đối tượng có thể thay đổi.
- Nhận biết phụ thuộc ẩn vào thời gian, số ngẫu nhiên, trạng thái toàn cục, tệp, cơ sở dữ liệu hoặc đối tượng mutable.
- Viết và kiểm thử các phép biến đổi dữ liệu Java theo hướng hàm thuần, rồi đặt thao tác I/O ở ranh giới chương trình.

## 2. Hàm thuần là gì?

Một hàm được xem là thuần khi **cả hai** điều kiện sau đúng:

1. **Cùng đầu vào về giá trị và trạng thái có liên quan luôn cho cùng kết quả.** Hàm không tự ý đọc trạng thái ngoài có thể thay đổi giữa các lần gọi. Với một đầu vào hợp lệ, kết quả được quyết định chỉ bởi đầu vào; nếu hàm báo lỗi, hành vi lỗi cũng phải nhất quán theo đầu vào.
2. **Không làm thay đổi trạng thái quan sát được ngoài hàm.** Không sửa tham số mutable hoặc biến dùng chung, không ghi file/database, không in log ra console, không gửi HTTP request. Việc tạo đối tượng cục bộ phục vụ tính toán là bình thường; vấn đề là biến đổi đó có lộ ra và ảnh hưởng nơi khác hay không.

Ví dụ toán học **f(x) = x × x**: với x = 3, kết quả luôn là 9. Khi hàm chỉ tính rồi trả kết quả, ta có thể thay lời gọi bằng chính giá trị kết quả mà không đổi hành vi chương trình ở ngữ cảnh tương ứng. Tính chất này gọi là **khả năng thay thế bằng giá trị (referential transparency)**.

~~~java
static int square(int x) {
    return x * x;
}
~~~

Hàm trên thuần trong miền giá trị kiểu **int** của Java: kể cả phép nhân tràn số nguyên, kết quả vẫn được Java xác định theo cùng toán hạng. Tuy nhiên, phép tràn có thể khiến kết quả khác bình phương toán học mong đợi; cần chọn kiểu dữ liệu hoặc kiểm tra tràn phù hợp với nghiệp vụ.

**“Cùng đầu vào” không đơn giản là cùng địa chỉ tham chiếu.** Nếu truyền một đối tượng có nội dung thay đổi, hai lần gọi nhận cùng tham chiếu vẫn có thể thấy hai trạng thái khác nhau. Muốn có tính ổn định, hãy xác định rõ dữ liệu đầu vào, vòng đời và khả năng bị sửa đồng thời.

## 3. Kết quả xác định chưa đủ để trở thành hàm thuần

Đoạn sau cho cùng kết quả số học nhưng vẫn có tác dụng phụ:

~~~java
static int twiceAndPrint(int x) {
    System.out.println("Computing " + x);
    return x * 2;
}
~~~

Với x = 5, giá trị trả về luôn là 10; nhưng gọi hai lần sẽ in hai dòng. Nếu thay lời gọi bằng hằng số 10, chương trình mất các dòng in: vì thế hàm **không thuần**.

Ngược lại, hàm sau không sửa dữ liệu nhưng vẫn có phụ thuộc ẩn:

~~~java
static boolean isExpired(java.time.Instant deadline) {
    return java.time.Instant.now().isAfter(deadline);
}
~~~

Cùng đối số **deadline**, kết quả có thể đổi theo thời gian. Cách cải tiến là đưa thời điểm quan sát vào thành **dữ liệu đầu vào tường minh**:

~~~java
static boolean isExpired(java.time.Instant deadline,
                         java.time.Instant now) {
    return now.isAfter(deadline);
}
~~~

Hàm thứ hai thuần nếu các đối số là các giá trị **Instant** bất biến. Lưu ý: chỉ truyền một đối tượng **Clock** hoặc **Random** vào hàm rồi gọi phương thức của nó chưa chắc làm hàm thuần; đối tượng đó vẫn có thể đại diện cho nguồn trạng thái thay đổi. Muốn thuần, hãy truyền **giá trị thời gian đã đọc**, **giá trị ngẫu nhiên đã sinh**, hoặc mô hình trạng thái đầu vào/đầu ra tường minh.

| Trường hợp | Cùng đầu vào cho cùng kết quả? | Không tác dụng phụ? | Thuần? |
| --- | --- | --- | --- |
| **x → x * 2** trên **int** | Có | Có | Có |
| Tính rồi **System.out.println(...)** | Có về giá trị trả về | Không | Không |
| Đọc **Instant.now()** trong hàm | Không đảm bảo | Có thể có | Không |
| Đọc biến **static** mutable | Không đảm bảo | Có thể có | Không |
| Sửa **List** truyền vào rồi trả kích thước | Không đảm bảo | Không | Không |
| Tạo **ArrayList** cục bộ, trả bản kết quả mới | Có nếu đầu vào ổn định | Có | Có |

Bảng nói về hành vi quan sát được; nó không có nghĩa mọi hàm dùng đối tượng, tạo bộ nhớ hoặc ném ngoại lệ đều không thuần.

## 4. Ví dụ Java 17 chạy độc lập

Tạo file **PureFunctionDemo.java** với nội dung sau:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class PureFunctionDemo {
    static int sumSquares(List<Integer> values) {
        return values.stream()
                .mapToInt(value -> value * value)
                .sum();
    }

    static String normalize(String text) {
        return text.strip().toLowerCase(Locale.ROOT);
    }

    static List<Integer> append(List<Integer> source, int item) {
        List<Integer> copy = new ArrayList<>(source);
        copy.add(item);
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        List<Integer> original = List.of(1, 2, 3);

        System.out.println(sumSquares(original));
        System.out.println(sumSquares(original));
        System.out.println(normalize("  JAVA  "));
        System.out.println(append(original, 4));
        System.out.println(original);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PureFunctionDemo.java
java PureFunctionDemo
~~~

Đầu ra chính xác:

~~~text
14
14
java
[1, 2, 3, 4]
[1, 2, 3]
~~~

**Giải thích:**

- **sumSquares** chỉ đọc danh sách đầu vào rồi tính tổng bình phương. Với **List.of(1, 2, 3)**, tổng là 1 + 4 + 9 = 14 trong cả hai lần gọi. Ví dụ giả định các phần tử khác null và phép toán trong miền phù hợp; với số lớn, cần cân nhắc tràn **int**.
- **normalize** xử lý chuỗi, vốn là giá trị bất biến. **strip()** loại khoảng trắng đầu/cuối và **toLowerCase(Locale.ROOT)** làm cho quy tắc chuyển chữ thường độc lập với locale mặc định của máy chạy. Tham số null sẽ gây **NullPointerException** theo cùng đầu vào.
- **append** tạo danh sách mới và không thêm trực tiếp vào **source**. **List.copyOf** trả về danh sách không cho phép sửa phần tử thông qua các phương thức như **add**; với phần tử kiểu **Integer** bất biến ở ví dụ này, đây là một đầu ra an toàn để chia sẻ. **List.copyOf** sao chép tham chiếu phần tử chứ không tự động sao chép sâu các đối tượng mutable.
- **main** thực hiện in ra console nên **main** không thuần. Việc đặt I/O ở bên ngoài các phép tính cho phép lõi xử lý vẫn thuần và dễ kiểm thử.

**Giới hạn hợp đồng:** các phương thức minh họa nêu trên được xem là thuần với dữ liệu đầu vào không bị thay đổi trong khi tính toán. Chẳng hạn **sumSquares** nhận một **List<Integer>** có thể sửa được; nếu luồng khác thay danh sách trong lúc gọi, kết quả hoặc ngoại lệ có thể thay đổi theo lịch thực thi. Hàm không tự bảo đảm bất biến cho tham số do bên ngoài sở hữu.

## 5. Đầu vào mutable và trạng thái ẩn

### 5.1. Thay đổi tham số là tác dụng phụ

~~~java
static int addAndCount(List<String> names, String name) {
    names.add(name);
    return names.size();
}
~~~

Nếu **names** ban đầu chứa một phần tử, gọi cùng **name** hai lần trên **chính danh sách đó** có thể lần lượt trả về 2 và 3. Hàm vừa làm biến đổi đầu vào, vừa gây phụ thuộc lịch sử gọi.

Có thể chuyển sang cách trả kết quả mới, để bên gọi quyết định có thay biến của mình hay không:

~~~java
static List<String> withName(List<String> names, String name) {
    List<String> copy = new java.util.ArrayList<>(names);
    copy.add(name);
    return List.copyOf(copy);
}
~~~

**withName** không sửa danh sách gốc, nhưng khi truyền dữ liệu tham chiếu có thể bị thay đổi đồng thời thì vẫn cần hợp đồng đầu vào ổn định. **List.copyOf** cũng không chấp nhận phần tử null; đó là quyết định của API cần xét khi thiết kế.

### 5.2. Biến static mutable khiến đầu vào bị thiếu

~~~java
static int runningTotal = 0;

static int addAndRecord(int amount) {
    runningTotal += amount;
    return runningTotal;
}
~~~

Cùng **amount = 5**, kết quả lần một có thể là 5, lần hai là 10. Hàm phụ thuộc **runningTotal** và đồng thời sửa nó. Thay bằng chuyển trạng thái một cách tường minh:

~~~java
static int nextTotal(int currentTotal, int amount) {
    return currentTotal + amount;
}
~~~

Bên gọi có thể dùng **total = nextTotal(total, 5)** để cập nhật trạng thái của mình ở lớp điều phối. Hàm **nextTotal** vẫn thuần: trạng thái cũ là đầu vào, trạng thái mới là kết quả. Đây là ý tưởng nền tảng khi xử lý state bằng reducer hoặc mô hình sự kiện.

### 5.3. Bất biến ở lớp ngoài chưa chắc là bất biến sâu

Một biến **final** chỉ ngăn gán lại tham chiếu; **final List<String> items = new ArrayList<>()** vẫn cho phép **items.add(...)**. Một **List.unmodifiableList(...)** là lớp nhìn không cho sửa qua wrapper, nhưng dữ liệu gốc có thể còn bị sửa từ một tham chiếu khác. **List.copyOf(...)** tạo snapshot về cấu trúc danh sách trong trường hợp thông thường, song không sao chép sâu phần tử mutable. **record** cũng không tự tạo bất biến sâu nếu component giữ mảng hoặc danh sách mutable.

Khi thiết kế đầu vào thuần, ưu tiên **String**, số, **Instant**, **LocalDate**, enum, record chứa các giá trị bất biến, hoặc snapshot dữ liệu cần thiết. Với object graph phức tạp, định nghĩa rõ quyền sở hữu, việc sao chép và mức bất biến mong muốn.

## 6. Hàm thuần trong Lambda, Stream và nghiệp vụ

Cú pháp lambda **không tự động bảo đảm** tính thuần. Lambda sau không thuần vì thao tác trên trạng thái chung:

~~~java
List<String> names = List.of("An", "Binh");
names.forEach(name -> System.out.println(name));
~~~

**forEach** được dùng chủ đích cho tác dụng phụ. Trong khi đó, phép biến đổi dưới đây dễ suy luận hơn vì chỉ xây dữ liệu kết quả:

~~~java
List<String> upper = names.stream()
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();
~~~

**Stream.toList()** có từ Java 16 và trả về danh sách không thể sửa qua các phương thức thay đổi của **List**. Nó không làm cho mọi phần tử thành bất biến sâu. Lambda đọc một giá trị được capture theo quy tắc **effectively final** vẫn có thể không thuần nếu giá trị đó là tham chiếu đến đối tượng mutable.

Một quy trình điển hình tách thành ba vùng:

1. **Đọc** dữ liệu tại ranh giới: HTTP request, database, file, đồng hồ hệ thống hoặc nguồn ngẫu nhiên.
2. **Tính toán thuần** với các giá trị đã thu thập: chuẩn hóa, kiểm tra quy tắc, định giá, nhóm, lọc, tính tổng, chuyển trạng thái.
3. **Thực hiện hiệu ứng**: lưu kết quả, gửi thông báo, ghi log hoặc trả HTTP response.

Ví dụ, để đánh giá hết hạn của đơn hàng: lớp ngoài lấy **Instant.now()** một lần, rồi gọi **isExpired(deadline, now)**. Các phép tính trong lõi trở nên tái lập được bằng cách truyền lại đúng cặp giá trị ở test.

## 7. Giá trị thực tế và giới hạn

- **Dễ kiểm thử:** có thể tạo bảng cặp đầu vào/đầu ra và assert trực tiếp, không cần mock đồng hồ, network hay database bên trong hàm tính toán.
- **Dễ suy luận:** kết quả ít phụ thuộc thứ tự gọi; refactor và tái sử dụng an toàn hơn khi hợp đồng đầu vào rõ ràng.
- **Dễ song song hóa:** nếu không cùng sửa trạng thái chia sẻ, nhiều phép tính độc lập ít gây race condition hơn. Tuy vậy vẫn cần quan tâm đầu vào mutable và chi phí đồng bộ/luồng.
- **Có thể memoize:** cache theo đầu vào phù hợp khi hàm thuần và đầu vào có biểu diễn khóa ổn định. Một cache kết quả của hàm đọc thời gian hay giá dữ liệu trực tiếp có thể làm trả kết quả cũ sai kỳ vọng.
- **Không phải mọi hàm đều cần thuần:** lưu database, ghi file và log là các hiệu ứng cần thiết của ứng dụng. Mục tiêu là đặt các hiệu ứng ở nơi rõ ràng, giữ phần lớn logic nghiệp vụ có thể tính toán độc lập.
- **Không đánh đồng thuần với hiệu năng:** sao chép dữ liệu để tránh mutation có chi phí bộ nhớ và thời gian. Chọn cấu trúc dữ liệu, kích thước snapshot và ranh giới bất biến theo thực tế.

## 8. Kiểm tra tính thuần khi review code

Hãy kiểm tra lần lượt:

1. Hàm có đọc **System.currentTimeMillis()**, **Instant.now()**, **Math.random()**, biến static mutable, singleton có trạng thái, cấu hình có thể cập nhật hoặc dữ liệu từ I/O không?
2. Hàm có sửa tham số, object được tham chiếu, collection, static field hay tài nguyên bên ngoài không?
3. Hàm có in console, ghi log, gọi API, gửi message hoặc thao tác database không?
4. Cùng các **giá trị đầu vào cố định**, bao gồm nội dung đối tượng, có tái lập kết quả được không? Có điều kiện race khiến câu trả lời thay đổi không?
5. Hàm có trả về đối tượng mutable dùng chung mà phía gọi sau đó có thể sửa, gây ảnh hưởng đến lần gọi kế tiếp không?
6. Nếu dùng **Stream** hoặc lambda, phần thân có chỉ biến đổi giá trị hay chứa side effect? **parallelStream()** có làm lộ vấn đề truy cập trạng thái chung không?

**Cách kiểm thử hữu ích:** dùng cùng bộ dữ liệu bất biến gọi nhiều lần và assert kết quả; giữ snapshot dữ liệu đầu vào để assert không bị đổi; chạy phép tính với dữ liệu đầu vào khác nhau, rồi gọi lại bộ dữ liệu ban đầu để phát hiện phụ thuộc lịch sử. Đây là cách tìm lỗi, nhưng không thể chứng minh tuyệt đối tính thuần chỉ qua vài test; vẫn phải đọc hợp đồng và các phụ thuộc.

## 9. Bài tập tự luyện

**Bài 1 — phân loại.** Xét ba phương thức:

~~~java
static int a(int x) { return x + 1; }

static int b(int x) {
    System.out.println(x);
    return x + 1;
}

static long c(long offset) {
    return System.currentTimeMillis() + offset;
}
~~~

**Đáp án:** **a** thuần theo phép toán **int**; **b** có đầu ra số xác định nhưng có hiệu ứng console; **c** phụ thuộc đồng hồ hệ thống nên không bảo đảm cùng đầu vào cho cùng đầu ra. Chỉ **a** thỏa cả hai điều kiện.

**Bài 2 — sửa thiết kế.** Một hàm **discountPrice** đang đọc tỷ lệ giảm giá từ biến static mutable và tự ghi log mỗi lần tính. Hãy đổi thành **discountPrice(price, rate)** chỉ tính kết quả, chuyển thao tác đọc cấu hình và log sang lớp gọi. Xác định rõ cách làm tròn và kiểu dữ liệu tiền tệ (ví dụ **BigDecimal**) theo yêu cầu nghiệp vụ; không dùng phép tính **double** như lời giải mặc định cho tiền.

**Bài 3 — suy luận về List.** Nếu **List<Integer> xs = new ArrayList<>(List.of(1, 2))** được truyền vào hàm chỉ đọc phần tử, rồi một nơi khác gọi **xs.add(3)** trước lần tính kế tiếp, vì sao kết quả có thể khác dù cùng biến **xs**? Trả lời: danh tính tham chiếu không đổi nhưng **giá trị dữ liệu** đã đổi; phải xét đầu vào theo trạng thái quan sát được, hoặc dùng snapshot/bất biến thích hợp.

## 10. Ghi nhớ

**Hàm thuần = kết quả chỉ do đầu vào quyết định + không tác dụng phụ quan sát được.** Hai điều kiện này độc lập và đều cần thiết. Trong Java, tính thuần là tính chất của **hành vi và hợp đồng dữ liệu**, không phải từ khóa ngôn ngữ, cũng không tự phát sinh khi viết lambda, Stream, **final** hay **record**. Chuyển phụ thuộc thay đổi thành **giá trị đầu vào tường minh**, tạo kết quả mới thay vì sửa dữ liệu được chia sẻ, và đặt I/O ở ranh giới chương trình để code dễ kiểm thử, tái lập và bảo trì.
