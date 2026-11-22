# peek() để quan sát khi gỡ lỗi trong Java Stream

## 1. peek() là gì và được dùng để làm gì?

Trong Java, **Stream.peek(Consumer<? super T> action)** tạo ra một **intermediate operation** (thao tác trung gian) trả về một Stream khác có các phần tử cùng kiểu T. Khi một phần tử thực sự được xử lý qua bước này, action có thể nhận phần tử ấy để **quan sát**: in log, xem trạng thái trước/sau một bước biến đổi, kiểm tra điều kiện lọc hay hỗ trợ đặt breakpoint trong IDE.

Một đoạn pipeline điển hình:

~~~java
List<String> result = words.stream()
        .peek(word -> System.out.println("Before: " + word))
        .map(String::strip)
        .peek(word -> System.out.println("After: " + word))
        .filter(word -> !word.isBlank())
        .toList();
~~~

Đây là **đoạn minh họa**, giả định words là List<String> không chứa null và đã import List. Việc ghi log cho thấy giá trị chảy qua hai vị trí: trước và sau khi strip. **peek không biến đổi phần tử theo hợp đồng của Stream**; bước map mới tạo giá trị mới từ phần tử.

Tài liệu Java nhấn mạnh **peek chủ yếu nhằm hỗ trợ gỡ lỗi**. Nó không phải nơi đáng tin cậy để ghi dữ liệu nghiệp vụ, gửi thông báo bắt buộc, tính tổng, cập nhật cache hay đếm các bản ghi phải được xử lý đủ. Lý do không chỉ là quy ước về code sạch: **Stream được phép tối ưu, ngắn mạch và song song hóa**, khiến việc thực thi side effect trong peek không được đảm bảo theo cách một vòng lặp tường minh thường mang lại.

**Câu cần ghi nhớ:** peek phù hợp để **nhìn** dữ liệu khi pipeline thực sự đi qua bước đó; không nên dùng peek để **định nghĩa kết quả** của pipeline hay công việc bắt buộc phải xảy ra.

## 2. Chữ ký và vị trí của peek trong chuỗi Stream

Chữ ký khái quát trong Stream<T>:

~~~java
Stream<T> peek(Consumer<? super T> action);
~~~

Đây là **chữ ký API rút gọn** để giải thích, không phải chương trình độc lập. Các yếu tố:

- **Stream<T>**: kiểu phần tử vẫn là T trước và sau peek. Ví dụ một Stream<Order> vẫn là Stream<Order>.
- **Consumer<? super T>**: action nhận phần tử và có SAM **void accept(T)**; nó không trả về giá trị để thay thế phần tử.
- **Intermediate operation**: giống map hoặc filter, peek trả Stream mới; bản thân việc khai báo pipeline chưa bắt đầu xử lý toàn bộ dữ liệu.
- **Lazy**: công việc được kích hoạt bởi terminal operation như toList, collect, forEach, reduce, findFirst, count, nhưng **các bước không bắt buộc được gọi cho mọi phần tử**.
- **Pipeline**: nếu có nhiều peek, từng peek chỉ quan sát giá trị ở vị trí tương ứng với các thao tác trước/sau.

Ví dụ một pipeline về mặt ý tưởng:

~~~text
Stream<String> nguồn
    |
    v
peek("raw")               -> quan sát giá trị ban đầu
    |
    v
map(String::strip)        -> tạo String đã chuẩn hóa
    |
    v
peek("normalized")        -> quan sát giá trị sau map
    |
    v
filter(notBlank)          -> loại phần tử không thỏa
    |
    v
peek("accepted")          -> quan sát phần tử còn lại
    |
    v
toList()                  -> yêu cầu kết quả cuối
~~~

Đây là **sơ đồ khái niệm**, không phải cú pháp Java. Đặt peek **trước filter** để nhìn cả phần tử bị loại; đặt peek **sau filter** để nhìn chỉ những phần tử tiếp tục đi qua bước này.

**Vị trí quyết định ngữ nghĩa log**. Không nên thấy một log "accepted" rồi suy ra phần tử đã hoàn thành toàn bộ bước xử lý tiếp theo: nếu terminal operation hoặc các bước sau thất bại, log ở peek chỉ chứng minh phần tử đã đến vị trí đó trong một lần thực thi cụ thể.

## 3. Ví dụ Java 17: quan sát trước/sau map và filter

Tạo tệp **PeekTraceDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;

public class PeekTraceDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "  Java  ", "Go", "  Kotlin ", "", " Java ");

        List<String> result = words.stream()
                .peek(s -> System.out.println("source=[" + s + "]"))
                .map(String::strip)
                .peek(s -> System.out.println("strip=[" + s + "]"))
                .filter(s -> s.length() >= 4)
                .peek(s -> System.out.println("accepted=[" + s + "]"))
                .map(s -> s.toUpperCase(Locale.ROOT))
                .toList();

        System.out.println("Result: " + result);
    }
}
~~~

Chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 PeekTraceDemo.java
java PeekTraceDemo
~~~

Stdout trong pipeline tuần tự với thao tác filter cần xét từng phần tử:

~~~text
source=[  Java  ]
strip=[Java]
accepted=[Java]
source=[Go]
strip=[Go]
source=[  Kotlin ]
strip=[Kotlin]
accepted=[Kotlin]
source=[]
strip=[]
source=[ Java ]
strip=[Java]
accepted=[Java]
Result: [JAVA, KOTLIN, JAVA]
~~~

**Đọc kết quả theo từng phần tử:**

1. **"  Java  "** xuất hiện nguyên văn ở source, được strip thành "Java", thỏa độ dài >= 4 nên đến accepted, sau đó chuyển thành "JAVA".
2. **"Go"** được strip thành "Go", không đủ bốn ký tự; vì vậy không có log accepted của Go.
3. **"  Kotlin "** trở thành "Kotlin", đi qua filter rồi chuyển chữ hoa.
4. Chuỗi rỗng đi qua hai log đầu nhưng bị filter loại.
5. **" Java "** tạo thêm "JAVA" thứ hai sau chuẩn hóa.

Trong một **pipeline tuần tự** dạng này, log phản ánh quá trình xử lý các phần tử được tiêu thụ và tương quan trước/sau từng thao tác. Tuy nhiên, **đừng suy rộng từ ví dụ này** rằng mỗi loại terminal operation, nguồn dữ liệu hoặc stream song song đều đảm bảo số lần gọi peek giống nhau. Java Stream có các tối ưu và quy tắc ngắn mạch được phân tích bên dưới.

**Vì sao không dùng peek để chuẩn hóa?** Một action như **s -> s = s.strip()** chỉ gán lại biến tham số lambda cục bộ, không đổi phần tử của stream. Muốn thay thế phần tử, dùng **map(String::strip)**.

## 4. Lazy evaluation: chỉ tạo pipeline thì peek chưa chạy

Một intermediate operation **không chủ động duyệt nguồn** khi bạn khai báo nó. Dữ liệu thường chỉ được yêu cầu khi terminal operation bắt đầu tiêu thụ stream.

Tạo tệp **PeekLazyDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class PeekLazyDemo {
    public static void main(String[] args) {
        System.out.println("create pipeline");

        Stream<String> pipeline = List.of("a", "bb", "ccc")
                .stream()
                .peek(s -> System.out.println("visited: " + s))
                .filter(s -> s.length() > 1);

        System.out.println("before terminal");
        long count = pipeline.count();
        System.out.println("count: " + count);
    }
}
~~~

Chạy:

~~~bash
javac PeekLazyDemo.java
java PeekLazyDemo
~~~

Stdout:

~~~text
create pipeline
before terminal
visited: a
visited: bb
visited: ccc
count: 2
~~~

Giải thích:

- Ở bước khai báo **pipeline**, Java đã tạo chuỗi thao tác, nhưng peek chưa in dòng "visited".
- **count()** là terminal operation. Với ví dụ có **filter(s -> s.length() > 1)**, Java phải xét từng phần tử để biết có bao nhiêu phần tử còn lại; các phần tử đi qua peek trước filter.
- Vì ba phần tử nguồn đều được xét, có ba dòng visited. Trong đó chỉ hai phần tử "bb" và "ccc" thỏa điều kiện, nên count bằng 2.
- Pipeline Stream chỉ được tiêu thụ một lần; sau count, không được gọi lại terminal operation trên cùng đối tượng pipeline đã dùng.

**Lưu ý:** Không phải cứ có terminal operation là mọi peek đều sẽ chạy. Ví dụ trên được chọn để việc xét dữ liệu là cần thiết; trường hợp count trên nguồn biết trước kích thước có thể được tối ưu mà không hề duyệt qua peek.

## 5. Bẫy lớn: count() có thể không thực thi peek

Từ các phiên bản Java hiện đại, Stream có thể **tính kết quả count() mà không duyệt từng phần tử** nếu nguồn đã biết chính xác kích thước và pipeline không thay đổi số lượng. Vì peek về mặt hợp đồng không thay đổi các phần tử hoặc kích thước, Java có thể bỏ qua toàn bộ action của peek.

Ví dụ:

~~~java
long size = List.of("a", "bb", "ccc")
        .stream()
        .peek(s -> System.out.println("debug: " + s))
        .count();

System.out.println(size);
~~~

Đây là **đoạn minh họa** trong một phương thức có import List. Trong Java 17, triển khai Stream trên danh sách có kích thước xác định có thể tính ngay **3** mà không gọi Consumer trong peek. Vì thế, **không thể khẳng định luôn có ba dòng debug**. Chỉ dựa vào một terminal operation kiểu count để “bắt buộc” việc log của peek chạy là sai.

Nhìn từ hợp đồng Stream:

~~~text
Có nguồn kích thước xác định, không thao tác đổi số phần tử:
  count() có thể lấy kích thước trực tiếp
  -> không cần duyệt từng phần tử
  -> peek có thể không chạy

Có filter làm thay đổi khả năng giữ phần tử:
  để biết count chính xác cần đánh giá predicate
  -> thông thường pipeline phải duyệt các phần tử liên quan
~~~

**Điểm quan trọng:** peek là **intermediate operation** nhưng Java không hứa việc tạo tác động phụ ở peek cho mọi phần tử nếu kết quả đầu cuối có thể được xác định mà không thực thi thao tác ấy. Chức năng của pipeline được mô tả bởi dữ liệu đầu ra, không phải bởi mọi dòng log ngẫu nhiên.

Trong nhiều trường hợp, tối ưu của Stream có thể loại bỏ không chỉ peek mà cả một số bước khác nếu kết quả terminal operation không phụ thuộc vào chúng và các điều kiện tối ưu được đáp ứng. Không nên viết code mà tính đúng nghiệp vụ phụ thuộc vào side effect của các bước trung gian.

## 6. Short-circuit: một số phần tử không cần được nhìn thấy

Các terminal operation như **findFirst**, **findAny**, **anyMatch**, **allMatch**, **noneMatch**, hoặc những intermediate operation như **limit** có thể làm pipeline **dừng sớm**.

Nếu chỉ cần phần tử đầu tiên thỏa điều kiện, Java không nhất thiết phải đi hết nguồn.

Tạo tệp **PeekShortCircuitDemo.java**:

~~~java
import java.util.stream.IntStream;

public class PeekShortCircuitDemo {
    public static void main(String[] args) {
        int firstEven = IntStream.rangeClosed(1, 5)
                .peek(n -> System.out.println("visit=" + n))
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElse(-1);

        System.out.println("firstEven=" + firstEven);

        boolean found = IntStream.rangeClosed(1, 5)
                .peek(n -> System.out.println("check=" + n))
                .anyMatch(n -> n == 3);

        System.out.println("found=" + found);
    }
}
~~~

Chạy:

~~~bash
javac PeekShortCircuitDemo.java
java PeekShortCircuitDemo
~~~

Stdout với pipeline tuần tự có thứ tự encounter:

~~~text
visit=1
visit=2
firstEven=2
check=1
check=2
check=3
found=true
~~~

**Giải thích:**

- **findFirst()** cần phần tử chẵn đầu tiên, nên chỉ cần xét số 1 rồi số 2. Số 3, 4, 5 không cần đi tới peek trong pipeline đó.
- **anyMatch(n -> n == 3)** kết thúc ngay khi tìm được số 3, nên không cần tiếp tục kiểm tra số 4 và 5.
- Mỗi terminal operation ở ví dụ này hoạt động trên **một Stream riêng** vì Stream đã tiêu thụ không được tái sử dụng.

**Lưu ý về parallel stream:** khi chạy song song, hệ thống có thể đã xử lý nhiều phần tử trước khi tín hiệu dừng truyền đi. Đừng dựa vào số lượng log hay thứ tự quan sát chính xác trong parallel pipeline như kết quả của ví dụ tuần tự.

### 6.1. skip và limit thay đổi tập phần tử được quan sát

Nếu đặt peek sau một bước skip hoặc limit, nó chỉ nhìn những phần tử thực sự đến vị trí ấy. Nếu đặt peek **trước** skip/limit, bạn có thể thấy nhiều phần tử hơn. Nhưng các tối ưu có thể thay đổi việc thực thi action; không dùng số log làm nguồn sự thật cho dữ liệu đã xử lý.

Ví dụ minh họa:

~~~java
List<Integer> result = IntStream.rangeClosed(1, 6)
        .boxed()
        .skip(2)
        .limit(3)
        .peek(n -> System.out.println("selected=" + n))
        .toList();
~~~

Đây là đoạn minh họa cần import IntStream và List. Kết quả dữ liệu là **[3, 4, 5]**. peek được đặt sau skip/limit để hỗ trợ quan sát các phần tử đến bước chọn cuối; nó không nhất thiết quan sát toàn bộ nguồn [1, 2, 3, 4, 5, 6].

## 7. Stream thường xử lý theo từng phần tử, không theo từng dòng code

Người mới học có thể tưởng Java thực thi:

~~~text
Bước 1: peek đầu tiên cho toàn bộ phần tử
Bước 2: map cho toàn bộ phần tử
Bước 3: filter cho toàn bộ phần tử
Bước 4: peek cuối cho toàn bộ phần tử
~~~

Trong nhiều pipeline tuần tự đơn giản (stateless operations), Stream **gộp/fuse các bước xử lý** theo phần tử: một phần tử đi qua các bước cần thiết, rồi mới tới phần tử tiếp theo. Đó là lý do stdout của **PeekTraceDemo** có dạng:

~~~text
source=[  Java  ]
strip=[Java]
accepted=[Java]
source=[Go]
strip=[Go]
...
~~~

chứ không in tất cả source trước rồi mới tất cả strip.

Tuy nhiên, đây **không phải hình thức thực thi duy nhất**. Một số intermediate operation **stateful** như sorted hoặc distinct có thể cần bộ nhớ đệm, nhìn nhiều phần tử trước khi phát tiếp dữ liệu. Pipeline song song cũng có thể chia công việc theo nhiều task.

**Kết luận:** Dùng log peek để hiểu giá trị đi qua các stage, nhưng đừng viết logic nghiệp vụ giả định một mô hình thực thi từng bước/từng phần tử là bất biến với mọi loại Stream.

## 8. Đặt peek trước và sau sorted để hiểu stateful operation

Ví dụ sorted có thể đệm các giá trị rồi phát ra theo thứ tự mới. Tạo tệp **PeekSortedDemo.java**:

~~~java
import java.util.List;

public class PeekSortedDemo {
    public static void main(String[] args) {
        List<String> result = List.of("c", "a", "b")
                .stream()
                .peek(s -> System.out.println("before=" + s))
                .sorted()
                .peek(s -> System.out.println("after=" + s))
                .toList();

        System.out.println("result=" + result);
    }
}
~~~

Chạy:

~~~bash
javac PeekSortedDemo.java
java PeekSortedDemo
~~~

Stdout trong ví dụ tuần tự:

~~~text
before=c
before=a
before=b
after=a
after=b
after=c
result=[a, b, c]
~~~

Ở đây:

1. Nguồn cung cấp phần tử theo thứ tự **c, a, b**.
2. sorted cần có dữ liệu để tính thứ tự, nên ba log **before** xuất hiện trước các log **after** trong triển khai tuần tự này.
3. Sau sorted, các phần tử phát theo thứ tự tự nhiên **a, b, c**, được peek thứ hai quan sát.
4. Terminal **toList()** trả danh sách theo encounter order hiện có của stream.

Kỹ thuật đặt peek ở hai phía của sorted rất hữu ích để quan sát điểm thay đổi thứ tự, nhưng **không dùng nó để cam kết thứ tự các side effect trên parallel stream**.

**Một điểm dễ hiểu nhầm:** sorted thay đổi **thứ tự**, không nhất thiết thay đổi nội dung hoặc số lượng; filter có thể loại phần tử; distinct có thể loại bản sao; map thay đổi giá trị. Log phải được đọc trong ngữ cảnh của thao tác nằm trước/sau nó.

## 9. peek không thay thế map, filter hay forEach

Nhiều lỗi xảy ra khi dùng nhầm mục đích của các API:

| API | Vai trò | Kết quả |
| --- | --- | --- |
| **map(Function<T,R>)** | Biến đổi phần tử từ T sang R | Stream<R> |
| **filter(Predicate<T>)** | Giữ phần tử thỏa điều kiện | Stream<T> |
| **peek(Consumer<T>)** | Quan sát phần tử khi pipeline thực thi | Stream<T> |
| **forEach(Consumer<T>)** | Thao tác terminal cho mỗi phần tử đầu ra cần xử lý | void |
| **forEachOrdered(Consumer<T>)** | Terminal action theo encounter order của stream có thứ tự | void |
| **collect(...)** | Thu gom thành cấu trúc dữ liệu/kết quả | Tùy collector |
| **toList()** | Thu kết quả Stream thành List | List<T> |

Ví dụ **sai về ý định biến đổi**:

~~~java
// KHÔNG DÙNG peek để thay thế map.
Stream<String> pipeline = words.stream()
        .peek(s -> s.toUpperCase());
~~~

Đây là đoạn minh họa, giả định có Stream<String>. **String.toUpperCase()** trả một String mới; action của peek bỏ qua giá trị đó, nên phần tử ban đầu **không được thay thế**. Chương trình vẫn có thể biên dịch, nhưng không có biến đổi mà người viết mong muốn.

Cách đúng:

~~~java
Stream<String> pipeline = words.stream()
        .map(s -> s.toUpperCase(Locale.ROOT));
~~~

Đoạn minh họa cần import Locale và giả định words có kiểu phù hợp. Với String immutable, map mới đưa chuỗi đã đổi chữ hoa vào Stream đầu ra.

### 9.1. Sửa object mutable trong peek là một bẫy khác

Giả sử một đối tượng Order có setter:

~~~java
orders.stream()
        .peek(order -> order.setStatus("PAID"))
        .toList();
~~~

Đây là **đoạn phản mẫu minh họa**, giả định các kiểu/method tồn tại. Nó cố gắng dùng peek để cập nhật trạng thái nghiệp vụ. Có các rủi ro:

- Action trong peek có thể **không được chạy** ở những pipeline được tối ưu hoặc ngắn mạch.
- Thay đổi trạng thái của object có thể gây **side effect**, làm stream khó suy luận và dễ data race trong parallel stream.
- toList() trả danh sách tham chiếu các phần tử; không đảm bảo một transaction hoặc cập nhật trạng thái ngoài hệ thống đã thành công.
- Code che giấu mục đích cập nhật trong một phương thức có tên peek, làm khó review.

Nếu cần biến đổi dữ liệu, cân nhắc **map** tạo giá trị mới (ưu tiên immutable). Nếu cần cập nhật object hoặc gọi service, dùng quy trình tường minh có xử lý lỗi, transaction, đồng bộ hóa và kiểm thử; không đặt công việc bắt buộc trong peek.

### 9.2. forEach và forEachOrdered cũng cần dùng đúng ngữ cảnh

**forEach** là terminal operation áp dụng action cho các phần tử stream kết quả, nhưng với parallel stream không cam kết giữ encounter order. **forEachOrdered** có cam kết encounter order nếu Stream có encounter order; tuy vậy vẫn không biến pipeline thành transaction và không làm action thread-safe tự động.

Nếu mục tiêu là log đầu ra cuối cùng, một hướng rõ hơn có thể là tính kết quả trước, rồi duyệt kết quả theo thứ tự và log. Nếu muốn quan sát *giữa* các stage, peek là công cụ debugging thích hợp.

## 10. Dùng peek để xác định phần tử bị loại ở filter

Một pattern hữu ích khi gỡ lỗi các rule nghiệp vụ:

~~~java
List<Order> eligible = orders.stream()
        .peek(o -> debug("input", o))
        .filter(isPaid)
        .peek(o -> debug("after paid", o))
        .filter(isDomestic)
        .peek(o -> debug("after domestic", o))
        .toList();
~~~

Đây là **đoạn minh họa**, giả định đã định nghĩa Order, các Predicate và phương thức debug. Trong thực tế, một Order có thể không đạt điều kiện đầu và không bao giờ xuất hiện ở log "after paid". Một Order đạt paid nhưng không đạt domestic sẽ xuất hiện ở "after paid" mà không ở "after domestic".

**Đừng suy ra tại sao phần tử bị loại chỉ từ việc nó vắng ở log cuối**. Muốn biết lý do đầy đủ, có thể cần log/trace trực tiếp ở rule hoặc xây dựng kết quả kiểm tra có cấu trúc (**Decision**, **ValidationResult**, danh sách lý do từ chối). Chỉ dùng peek giữa filter cho biết phần tử **đã đi qua bước nào** khi action được chạy.

### 10.1. Khi có null element

Đoạn sau có thể ném NullPointerException:

~~~java
employees.stream()
        .peek(e -> System.out.println(e.name()))
        .filter(Objects::nonNull)
        .toList();
~~~

Đây là **đoạn minh họa cố ý nguy hiểm**: peek đọc thuộc tính trước khi loại phần tử null. Nếu nguồn chứa null, cần đặt guard trước khi dereference:

~~~java
employees.stream()
        .filter(Objects::nonNull)
        .peek(e -> System.out.println(e.name()))
        .toList();
~~~

Cần import Objects và có Employee.name() tương ứng. **Đặt peek an toàn** cũng phải tuân thủ quy tắc null, ngoại lệ và dữ liệu đầu vào như map và filter.

Nếu dùng log để thấy cả null input, hãy in chính đối tượng thay vì gọi thuộc tính khi không an toàn:

~~~java
employees.stream()
        .peek(e -> System.out.println("input=" + e))
        .filter(Objects::nonNull)
        .toList();
~~~

Đây là đoạn minh họa. Lúc này **String.valueOf(Object)** được dùng khi nối chuỗi; với null, nó tạo chữ "null" thay vì dereference Employee. Nhưng việc gọi **toString()** của một object khác null vẫn có thể có side effect hoặc ném exception nếu lớp định nghĩa method không an toàn.

## 11. Parallel stream: không dùng thứ tự log để suy luận thứ tự dữ liệu

Với **parallelStream()** hoặc **stream().parallel()**, các phần tử có thể được xử lý bởi nhiều task/worker khác nhau:

~~~java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.parallelStream()
        .peek(n -> System.out.println(
                Thread.currentThread().getName() + ": " + n))
        .map(n -> n * 2)
        .toList();

System.out.println(result);
~~~

Đây là đoạn minh họa cần import List. Kết quả List vẫn giữ encounter order của nguồn trong trường hợp có thứ tự: **[2, 4, 6, 8, 10]**. Tuy nhiên, **thứ tự các dòng peek, tên thread và cách phân chia phần tử không được cố định**, nên không nên viết một stdout exact cho log song song.

Phân biệt:

- **Thứ tự kết quả** của terminal operation có thể được định nghĩa bởi hợp đồng API và encounter order.
- **Thứ tự thời gian thực thi action của peek** không nhất thiết trùng thứ tự đó.
- **Thread thực thi** action có thể thay đổi giữa các phần tử.
- **Visibility và an toàn trạng thái** của object bị action đọc/ghi vẫn cần được xét riêng.

Ví dụ đếm bằng `int[] counter = {0};` rồi `peek(x -> counter[0]++)` trong parallel stream là phản mẫu: cập nhật không nguyên tử, có thể bị mất lần tăng; quan trọng hơn, peek còn có thể bị tối ưu bỏ qua. Ngay cả dùng AtomicInteger cũng **không biến peek thành phương thức đếm nghiệp vụ đáng tin** khi API không cam kết gọi action cho mọi phần tử.

Nếu mục tiêu là **đếm phần tử**, dùng **count()**. Nếu mục tiêu là tính tổng, dùng **mapToInt(...).sum()**, **reduce** hoặc collector thích hợp; nếu cần telemetry bắt buộc, tích hợp ở một điểm thực thi có hợp đồng rõ ràng.

## 12. Những giới hạn khác của side effect trong Stream

### 12.1. Stateless và non-interfering là nguyên tắc quan trọng

Behavioral parameters của Stream nên **non-interfering** (không sửa nguồn dữ liệu trong lúc pipeline đang duyệt) và phần lớn nên **stateless** (không phụ thuộc trạng thái mutable thay đổi giữa các lời gọi). Chèn side effect trong peek dễ đi ngược những nguyên tắc này.

Ví dụ không nên làm:

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));

values.stream()
        .peek(n -> values.add(n + 10))
        .toList();
~~~

Đây là **phản mẫu minh họa**, giả định đã import List và ArrayList. Nó sửa nguồn ArrayList trong lúc duyệt, có thể dẫn tới ConcurrentModificationException hoặc hành vi không xác định theo hợp đồng Stream. Đừng dùng peek để “vừa duyệt vừa thêm dữ liệu vào chính nguồn”.

**Đừng diễn giải mọi kết quả chạy thành guarantee**: có thể một thử nghiệm cụ thể trông như chạy xong, nhưng hành vi vẫn không phù hợp quy tắc non-interference.

### 12.2. Không dựa vào số lần gọi action

Tác động phụ của các behavioral parameters trong pipeline có thể bị bỏ qua nếu triển khai có thể tính kết quả theo cách tương đương. Ngắn mạch cũng làm một số phần tử không tới bước action. Do vậy:

- Không kiểm tra tính đúng của xử lý bằng cách **đếm số dòng peek**.
- Không dùng peek để ghi audit bắt buộc cho từng giao dịch.
- Không trông chờ action được chạy “đúng một lần cho mỗi phần tử nguồn”.
- Không lưu trạng thái phụ trong map/filter/peek rồi dùng nó để quyết định kết quả cuối.

Muốn làm rõ **đã xử lý thành công** trong hệ thống thật, hãy xác định ranh giới transaction/task riêng và log tại điểm có hợp đồng rõ, không chỉ dựa trên một bước trung gian của Stream.

### 12.3. Không nên xử lý lỗi bằng cách nuốt exception trong peek

Ví dụ:

~~~java
stream.peek(item -> {
    try {
        sendToRemoteService(item);
    } catch (Exception ignored) {
        // Bỏ qua lỗi.
    }
}).toList();
~~~

Đây là đoạn **phản mẫu**, không độc lập và giả định stream cùng sendToRemoteService có sẵn. Nếu gửi dữ liệu là công việc chính, đặt nó trong peek rồi nuốt lỗi sẽ gây trạng thái dữ liệu không nhất quán, rất khó nhận ra trong review.

Nếu action dùng để ghi debug có thể ném lỗi, nó có thể làm pipeline thất bại; nếu cần logging resilient, hãy dùng framework logging và chính sách vận hành phù hợp, tránh che lỗi nghiệp vụ vô tình. Một câu lệnh peek không phải ranh giới tách biệt cho exception hoặc transaction.

## 13. peek với sorted, distinct, limit và các bước stateful

Quan sát output của peek thường phụ thuộc vị trí:

| Pipeline | peek nhìn gì, về mặt ý định? | Lưu ý |
| --- | --- | --- |
| **peek → map** | Giá trị trước khi biến đổi | Map có thể trả kiểu khác |
| **map → peek** | Giá trị sau khi biến đổi | Nếu mapper tạo null, log phải chịu được null |
| **peek → filter** | Các phần tử đến bước trước lọc | Một số sẽ bị loại |
| **filter → peek** | Những phần tử qua được lọc | Không có nghĩa đã hoàn tất cả pipeline |
| **peek → sorted** | Thứ tự nguồn trong pipeline tuần tự | sorted có thể đệm trước khi phát |
| **sorted → peek** | Thứ tự sau sắp xếp | Parallel logging có thể không theo encounter order |
| **peek → distinct** | Phần tử trước khi loại bản sao | Có thể có trùng |
| **distinct → peek** | Phần tử đã qua distinct | Không cam kết đếm qua log |
| **limit → peek** | Những phần tử đến bước sau limit | Short-circuit có thể giảm số phần tử |
| **peek → count** | Có thể không thấy log nào | Nếu count tối ưu nhờ kích thước nguồn |

Bảng giúp xác định **đặt breakpoint ở đâu**. Nó không phải một tập hợp guarantee rằng Consumer của peek chắc chắn được gọi trong mọi trường hợp.

### 13.1. Dùng breakpoint thay vì thay đổi logic

Khi gỡ lỗi bằng IDE:

1. Đặt breakpoint ở lambda truyền cho peek để xem phần tử, thread và trạng thái ở bước cụ thể.
2. Dùng debugger inspect các biến/stack frame; nhận thức rằng trong pipeline song song nhiều thread có thể xen kẽ.
3. Khi điều tra một bug khó tái hiện, cân nhắc chuyển tạm sang **stream.sequential()** hoặc vòng lặp tường minh để kiểm tra thứ tự. Điều đó phục vụ chẩn đoán, không có nghĩa phiên bản production nên thay đổi song song hóa một cách không đánh giá.
4. Sau khi sửa lỗi, loại bỏ log tạm hoặc hạ log level để tránh chi phí chạy và nguy cơ lộ dữ liệu.

**Đừng làm debugging bằng cách thay đổi dữ liệu trong peek**. Nếu cần tái hiện sau một phép biến đổi, đặt peek trước/sau map, filter hay sorted là đủ để quan sát.

## 14. Gắn logging có ngữ cảnh cho pipeline

Một log tốt nên trả lời: “đang nhìn phần tử nào, ở giai đoạn nào, trong lần chạy nào?” Ví dụ:

~~~java
Function<String, String> normalize = String::strip;

List<String> cleaned = inputs.stream()
        .filter(Objects::nonNull)
        .peek(x -> logger.debug("stage=raw value={}", x))
        .map(normalize)
        .peek(x -> logger.debug("stage=normalized value={}", x))
        .filter(x -> !x.isBlank())
        .toList();
~~~

Đây là **đoạn minh họa**, giả định logger hỗ trợ cú pháp message placeholder, có imports Function, List, Objects và nguồn inputs phù hợp. **Không có logger được khai báo**, nên đừng copy nguyên làm tệp độc lập.

Để kiểm soát chi phí:

- Dùng **debug/trace level** cho thông tin tạm, tránh in dồn dập ở production.
- Không ghi **dữ liệu nhạy cảm** (token, mật khẩu, thông tin cá nhân), kể cả khi đang gỡ lỗi.
- Khi action tạo String lớn hoặc gọi **toString()** tốn kém, cân nhắc kiểm tra log level trước hoặc dùng API logging hỗ trợ xử lý tham số hiệu quả.
- Không mặc định logger thread-safe đồng nghĩa toàn bộ object được peek tham chiếu là thread-safe.
- Không lấy log từ peek làm audit chính thức vì JVM có thể bỏ action trong một số pipeline.

Nếu cần mô tả lý do phần tử bị loại, log ở **Predicate nghiệp vụ** hoặc tạo một **kết quả validation có cấu trúc** có thể rõ hơn; peek giữa các filter chỉ quan sát những phần tử đi qua từng giai đoạn.

## 15. So sánh peek với một vòng lặp tường minh

Đôi khi bạn **bắt buộc** phải thực hiện một hành động cho mỗi mục và xử lý lỗi theo từng mục. Một vòng lặp có ý định rõ ràng hơn:

~~~java
for (Order order : orders) {
    auditService.recordAttempt(order);
    if (policy.accepts(order)) {
        accepted.add(order);
    }
}
~~~

Đây là đoạn minh họa, giả định Order, auditService, policy và accepted đã được định nghĩa. Nếu audit phải chạy với mỗi order theo vòng lặp này, hành động được đặt trực tiếp trong flow; caller vẫn phải xử lý ngoại lệ/transaction đúng yêu cầu. Một vòng lặp tường minh cũng không tự có retry hay đồng bộ hóa, nhưng ít nhất không che việc bắt buộc trong một intermediate operation.

Nếu chỉ muốn xem dữ liệu **để gỡ lỗi**, Stream với peek thường ngắn và dễ đặt vào một pipeline đang có:

~~~java
List<Order> result = orders.stream()
        .filter(policy::accepts)
        .peek(o -> logger.debug("accepted candidate {}", o.id()))
        .toList();
~~~

Đoạn minh họa cần có các kiểu/phương thức/biến đã định nghĩa. Đây là **log quan sát**, không phải lời hứa rằng mỗi order hợp lệ đã được ghi audit thành công.

**Cân bằng thực hành:** Giữ pipeline khai báo cho logic biến đổi dữ liệu thuần; dùng công cụ quan sát có thể bật/tắt để tìm lỗi; dùng quy trình tường minh cho side effect bắt buộc, có thứ tự, khả năng retry và yêu cầu giao dịch.

## 16. Những lỗi phổ biến khi dùng peek

| Ngộ nhận/lỗi | Điều có thể xảy ra | Cách làm đúng |
| --- | --- | --- |
| Tạo stream().peek(...) rồi chờ log xuất hiện | Chưa có terminal operation nên chưa tiêu thụ dữ liệu | Chạy terminal operation phù hợp; nhớ có thể tối ưu |
| Dùng peek(...).count() để buộc action chạy | count có thể lấy kích thước mà không duyệt | Không dùng peek cho side effect bắt buộc |
| Nghĩ peek đổi phần tử | Consumer không tạo giá trị thay thế trong Stream | Dùng map cho biến đổi |
| Ghi database/cache/audit trong peek | Có thể bị bỏ, chạy không như mong đợi hoặc lặp tác động phụ | Tách công việc nghiệp vụ sang quy trình có hợp đồng |
| Cho rằng peek chạy với mọi phần tử nguồn | filter/limit/findFirst/anyMatch có thể dừng hoặc loại | Nhìn vị trí và terminal operation |
| Dựa vào thứ tự System.out.println trong parallel stream | Log có thể xen kẽ giữa thread | Dùng dữ liệu kết quả và API có encounter-order guarantee |
| Đặt peek đọc thuộc tính trước guard null | Có thể ném NullPointerException | Đặt filter(Objects::nonNull) trước hoặc kiểm tra trong action |
| Sửa ArrayList nguồn từ peek | Vi phạm non-interference, có thể ConcurrentModificationException | Không sửa nguồn khi đang duyệt |
| Đếm phần tử bằng counter++ trong peek | Race condition, action không được đảm bảo chạy | Dùng count() hoặc collector phù hợp |
| Giữ log verbose ở production | Tăng overhead, có nguy cơ lộ dữ liệu | Giảm log level, gỡ instrumentation tạm |
| Ghi nhận "đã xử lý" ngay trước bước tiếp theo | Bước sau có thể thất bại; log dễ gây hiểu nhầm | Ghi trạng thái nghiệp vụ ở ranh giới hoàn thành thực tế |

## 17. Checklist gỡ lỗi bằng peek

Trước khi thêm peek vào pipeline, hãy hỏi:

1. **Mục tiêu là quan sát hay cập nhật trạng thái?** Nếu cập nhật trạng thái bắt buộc, không dùng peek.
2. **Nguồn có null không?** Tránh dereference không kiểm tra trong log.
3. **Muốn thấy dữ liệu trước hay sau map/filter/sorted?** Đặt peek ở đúng chỗ.
4. **Terminal operation là gì?** Có chạy pipeline không? Có cho phép tính tắt như count không?
5. **Có findFirst, anyMatch hoặc limit không?** Nếu có, chỉ một phần nguồn có thể đi qua.
6. **Stream có chạy song song không?** Không suy luận theo thứ tự thời gian của log.
7. **Logger có side effect hoặc chi phí đáng kể không?** Giới hạn dung lượng và dữ liệu nhạy cảm.
8. **Cần dữ liệu để tái hiện bug không?** Có thể tách bước biến đổi hoặc dùng fixture/breakpoint thay vì chỉ nhìn console.
9. **Đang phụ thuộc vào số lần gọi peek để assert đúng?** Viết test kiểm tra dữ liệu đầu ra, không chỉ đếm dòng log.
10. **Sau khi gỡ lỗi xong có thể bỏ peek?** Hãy giữ pipeline thuần và dễ bảo trì.

## 18. Bài tập

### Bài 1: Dự đoán output có filter

Với danh sách **["a", "bb", "ccc"]**, viết pipeline **peek → filter(length >= 2) → peek → toList**. Dự đoán phần tử xuất hiện tại hai peek trong stream tuần tự và danh sách kết quả cuối.

Gợi ý: trước filter có a, bb, ccc; sau filter có bb, ccc. Lưu ý đây là dự đoán cho một pipeline cụ thể cần duyệt để xây dựng kết quả, không phải cam kết cho mọi tối ưu Stream.

### Bài 2: Vì sao peek với count không chạy?

Thử:

~~~java
List.of(1, 2, 3).stream()
        .peek(System.out::println)
        .count();
~~~

Đây là đoạn minh họa. Tại sao bạn có thể không thấy ba dòng số? Phân biệt giá trị **count = 3** với việc **action của peek có thực thi hay không**. Sau đó thêm filter theo một điều kiện khiến kích thước đầu ra không xác định trước và quan sát khác biệt.

### Bài 3: Quan sát trước/sau sorted

Cho **["z", "a", "m"]**. Viết **peek → sorted → peek → toList** và giải thích vì sao các log trước/sau sorted có thể tạo hai nhóm khác thứ tự trong pipeline tuần tự.

### Bài 4: Short-circuit

Dùng IntStream.rangeClosed(1, 100), thêm peek, filter số chia hết cho 7, rồi **findFirst()**. Dự đoán số đầu tiên được chọn. Vì sao các phần tử lớn hơn 7 không cần đi qua toàn bộ pipeline tuần tự?

### Bài 5: Biến đổi sai bằng peek

Cho String immutable, tại sao **peek(s -> s.toUpperCase())** không chuyển kết quả sang chữ hoa? Hãy viết lại bằng **map(s -> s.toUpperCase(Locale.ROOT))** và kiểm tra danh sách đầu ra.

### Bài 6: Thiết kế audit

Một hệ thống bắt buộc ghi audit cho từng giao dịch, bất kể giao dịch có vượt bộ lọc hay không. Vì sao không nên viết **orders.stream().peek(audit::record).filter(...).count()**? Hãy đề xuất quy trình có ranh giới audit rõ ràng và khả năng báo lỗi.

### Bài 7: Quan sát trong parallel pipeline

Viết một parallel stream và peek in số cùng tên thread. So sánh thứ tự log với thứ tự kết quả của **toList()** trên nguồn có encounter order. Giải thích vì sao không được dùng thứ tự log để tái tạo chính xác thứ tự kết quả.

## 19. Ghi nhớ

- **peek(Consumer)** là thao tác trung gian chủ yếu dùng để **quan sát** phần tử trong quá trình gỡ lỗi, không thay thế **map**, **filter** hay công việc nghiệp vụ bắt buộc.
- **Stream lazy:** khai báo pipeline chưa thực thi peek. Cần một terminal operation, nhưng điều đó **không bảo đảm** peek chạy trên mọi phần tử.
- **count có thể tối ưu bỏ traversal** khi kích thước đã biết; **findFirst/anyMatch/limit** có thể dừng sớm.
- **Thứ tự các log peek** không phải hợp đồng chung, đặc biệt với **sorted**, **parallel stream** và các tối ưu.
- **Không sử dụng side effect trong peek làm nguồn sự thật** để ghi audit, cập nhật trạng thái, đếm phần tử hoặc điều khiển nghiệp vụ.
- Dùng **map** để biến đổi, **filter** để chọn, **collect/toList** để tạo kết quả, và **quy trình tường minh** khi cần bảo đảm các side effect xảy ra.

Một câu hỏi đủ để chọn đúng công cụ: **“Nếu JVM không gọi action của peek trong một lần xử lý hợp lệ, ứng dụng có còn đúng không?”** Nếu câu trả lời là **không**, action ấy không nên được đặt trong peek.