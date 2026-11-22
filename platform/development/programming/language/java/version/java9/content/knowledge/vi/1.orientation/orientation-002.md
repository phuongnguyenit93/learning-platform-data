# Quan hệ giữa cải tiến ngôn ngữ, thư viện, công cụ và JVM

## Mục tiêu

Một phiên bản Java có thể mang đến nhiều loại thay đổi cùng lúc: cú pháp và quy tắc ngôn ngữ, API thư viện chuẩn, công cụ phát triển, định dạng bytecode và cách JVM vận hành. Hiểu đúng từng lớp giúp bạn biết thay đổi nào tác động đến mã nguồn, thay đổi nào chỉ cần JDK mới, và thay đổi nào ảnh hưởng đến cách ứng dụng được build hoặc chạy.

Sau bài này, bạn có thể:

- Phân biệt ngôn ngữ Java, Java SE API, công cụ JDK, công cụ build và JVM.
- Giải thích cách mã nguồn đi từ trình biên dịch đến bytecode rồi được JVM thực thi.
- Nhận diện các cải tiến từ Java 9 vẫn còn giá trị trong Java hiện đại.
- Chọn mức tương thích phù hợp khi biên dịch và chạy ứng dụng.
- Tránh nhầm một tính năng của công cụ hoặc JVM với tính năng của ngôn ngữ.

## 1. Các lớp tạo nên một nền tảng Java

Một chương trình Java thường đi qua nhiều lớp có trách nhiệm khác nhau:

| Lớp | Thành phần tiêu biểu | Trách nhiệm |
|---|---|---|
| Ngôn ngữ Java | Cú pháp, kiểu dữ liệu, biểu thức, interface, class | Quy định mã nguồn hợp lệ và ý nghĩa của chương trình |
| Java SE API | java.base, collections, streams, concurrency, I/O | Cung cấp các kiểu và dịch vụ chuẩn mà chương trình gọi |
| Công cụ JDK | javac, java, jar, jshell, jdeps, jlink | Biên dịch, khởi chạy, đóng gói, kiểm tra và tạo runtime image |
| Công cụ build | Gradle, Maven | Quản lý dependency, source set, tác vụ biên dịch, kiểm thử và đóng gói |
| JVM | Class loading, bytecode verification, JIT, garbage collection, thread scheduling | Nạp và thực thi bytecode, quản lý tài nguyên và tối ưu khi chạy |

Các lớp phối hợp với nhau nhưng không phải một khái niệm duy nhất.

- **Ngôn ngữ** trả lời câu hỏi: mã nguồn có hợp lệ và có ý nghĩa gì?
- **Thư viện** trả lời câu hỏi: chương trình có thể sử dụng những API nào?
- **Công cụ** trả lời câu hỏi: mã nguồn được biên dịch, phân tích, đóng gói và chạy bằng cách nào?
- **JVM** trả lời câu hỏi: bytecode được nạp và thực thi ra sao?
- **Gradle/Maven** điều phối các bước build và dependency trong một dự án.

JDK là bộ công cụ dành cho phát triển Java, bao gồm trình biên dịch, các công cụ và môi trường chạy cần thiết. JVM là máy ảo thực thi bytecode. Vì thế, nói “JDK mới có tính năng” chưa đủ chính xác: cần xác định tính năng đó thuộc ngôn ngữ, API, công cụ hay runtime.

## 2. Luồng từ mã nguồn đến chương trình đang chạy

Luồng cơ bản:

~~~text
Tệp .java
   |
   v
javac: phân tích cú pháp, kiểm tra kiểu và API
   |
   v
Tệp .class: Java bytecode
   |
   v
JAR / module path / class path
   |
   v
java launcher và JVM
   |
   v
Class loading -> verification -> linking -> initialization
   |
   v
Thực thi bytecode, JIT và quản lý bộ nhớ
~~~

### Bước 1: Trình biên dịch xử lý ngôn ngữ và API

Trình biên dịch đọc mã nguồn, kiểm tra cú pháp, kiểu dữ liệu, quyền truy cập và các quy tắc ngôn ngữ. Khi mã nguồn gọi một API như List.of hoặc Stream.takeWhile, trình biên dịch còn cần nhìn thấy khai báo API tương ứng trong nền tảng Java mục tiêu.

Một cải tiến cú pháp cần trình biên dịch hiểu cú pháp đó. Một API mới cần trình biên dịch nhìn thấy khai báo API và runtime cung cấp implementation tương ứng.

### Bước 2: Bytecode làm cầu nối đến JVM

Sau khi biên dịch, mã Java được chuyển thành bytecode trong các tệp .class. Bytecode không phải mã máy riêng cho một bộ xử lý cụ thể. JVM đọc định dạng class file, kiểm tra tính hợp lệ và thực thi các lệnh bytecode.

Mỗi thế hệ Java có thể nâng phiên bản class file hoặc bổ sung bytecode và quy tắc nền tảng. JVM cũ có thể không hiểu class file được tạo bởi JDK mới hơn. Đây là lý do một chương trình biên dịch thành công vẫn có thể không chạy được trên runtime quá cũ.

### Bước 3: JVM thực thi và tối ưu

JVM nạp lớp, xác minh bytecode, liên kết tham chiếu, khởi tạo lớp và thực thi chương trình. Trong quá trình chạy, JVM có thể biên dịch một số đoạn bytecode thành mã máy bằng JIT, quản lý heap, thu gom rác và điều phối luồng.

Những tối ưu như cách lưu trữ String hoặc cách garbage collector hoạt động có thể thay đổi mà không buộc người dùng sửa mã nguồn. Đây là thay đổi ở tầng runtime.

## 3. Các cải tiến Java 9 vẫn còn áp dụng

Java 9 mang đến thay đổi ở nhiều lớp. Một số cải tiến có giá trị sử dụng lâu dài và vẫn hiện diện trong các JDK hiện đại.

### Ngôn ngữ: private method trong interface

Từ Java 9, interface có thể khai báo private instance method hoặc private static method. Chúng cho phép các default method hoặc static method dùng chung logic nội bộ.

~~~java
interface PricePolicy {
    int discount(int price);

    default int finalPrice(int price) {
        return applyDiscount(price, discount(price));
    }

    private int applyDiscount(int price, int discount) {
        return Math.max(0, price - discount);
    }
}
~~~

Phương thức private không trở thành API mà lớp triển khai phải cung cấp và không được gọi trực tiếp từ mã bên ngoài interface. Nó giúp tránh lặp logic giữa nhiều default method. Đây là khả năng của ngôn ngữ và trình biên dịch; JVM vẫn thực thi bytecode được tạo ra.

### Thư viện: factory method cho collection

Java 9 bổ sung các factory method như List.of, Set.of và Map.of:

~~~java
List<String> names = List.of("Java", "JVM", "JDK");
~~~

Các collection tạo bởi những phương thức này không hỗ trợ thay đổi cấu trúc hoặc thay thế phần tử. Chúng cũng từ chối null; Set.of và Map.of từ chối phần tử hoặc khóa bị trùng theo hợp đồng API.

Điểm cần nhớ là collection không cho phép sửa cấu trúc, nhưng nếu phần tử bên trong là một object có trạng thái thay đổi thì trạng thái của object đó vẫn có thể thay đổi. Không nên đồng nhất collection không sửa được với mọi object chứa trong nó đều bất biến.

### Thư viện: Stream và Optional

Java 9 bổ sung một số API hữu ích:

- Stream.takeWhile(predicate) lấy phần đầu liên tiếp của stream khi điều kiện còn đúng.
- Stream.dropWhile(predicate) bỏ phần đầu liên tiếp thỏa điều kiện rồi trả về phần còn lại.
- Stream.ofNullable(value) tạo stream rỗng khi giá trị là null, hoặc stream có một phần tử khi giá trị khác null.
- Optional.stream() chuyển Optional thành stream có 0 hoặc 1 phần tử.
- Stream.iterate(seed, hasNext, next) tạo stream có điều kiện dừng.

Với stream có thứ tự, takeWhile khác filter: takeWhile dừng tại phần tử đầu tiên không thỏa điều kiện, trong khi filter vẫn tiếp tục xét các phần tử phía sau.

~~~java
List<Integer> result = Stream.of(1, 2, 3, 1, 4)
        .takeWhile(number -> number < 3)
        .collect(Collectors.toList());
~~~

Kết quả là [1, 2]. Hai số 1 và 4 ở cuối không được xét tiếp sau khi điều kiện sai tại số 3.

### Thư viện: Flow API và ProcessHandle

Java 9 bổ sung Flow API trong java.util.concurrent với các giao diện Publisher, Subscriber, Subscription và Processor. Đây là bộ giao diện chuẩn cho mô hình truyền dữ liệu bất đồng bộ có backpressure. Framework reactive có thể triển khai hoặc tích hợp các giao diện này; Flow không tự biến ứng dụng thành một hệ thống reactive hoàn chỉnh.

ProcessHandle cung cấp API chuẩn để truy vấn và thao tác với tiến trình của hệ điều hành, ví dụ lấy PID, thông tin tiến trình và các tiến trình con. API này hữu ích khi ứng dụng phải quản lý tiến trình bên ngoài theo cách có cấu trúc hơn.

### Công cụ JDK: JShell

JShell là môi trường tương tác cho phép thử biểu thức, câu lệnh và đoạn mã Java mà không cần tạo một project hoặc lớp main hoàn chỉnh. Nó hữu ích khi học API, kiểm tra nhanh một ý tưởng hoặc khám phá hành vi của một đoạn mã nhỏ.

JShell là công cụ phát triển. Việc chạy một biểu thức trong JShell không thay thế quy trình biên dịch, kiểm thử và đóng gói ứng dụng.

### Công cụ JDK: jlink và jdeps

jlink tạo runtime image tùy chỉnh bằng cách liên kết các mô-đun cần thiết cùng các phụ thuộc của chúng. Điều này giúp ứng dụng modular có thể phân phối một runtime phù hợp với phạm vi sử dụng thay vì luôn yêu cầu người dùng cài một bộ runtime đầy đủ.

jdeps là công cụ đã có từ JDK 8; trong hệ sinh thái mô-đun từ Java 9 trở đi, nó hỗ trợ phân tích dependency ở cấp class hoặc JAR và nhận diện quan hệ phụ thuộc mô-đun. Công cụ này hữu ích khi kiểm tra ứng dụng hoặc thư viện trong quá trình tổ chức sang JPMS.

### Công cụ biên dịch: tùy chọn --release

Tùy chọn javac --release cho phép chọn phiên bản Java mục tiêu một cách nhất quán: trình biên dịch kiểm tra cú pháp/ngôn ngữ, tạo class file tương thích và giới hạn API Java SE theo phiên bản được chọn.

Chỉ dùng -source và -target có thể chưa đủ để ngăn mã nguồn gọi một API chỉ xuất hiện ở JDK mới hơn. --release giải quyết cả phần API nền tảng được phép sử dụng.

Ví dụ, JDK mới có thể biên dịch mã cho Java 17:

~~~bash
javac --release 17 -d out src/PlatformExample.java
~~~

Mã được tạo có thể chạy trên runtime Java 17 trở lên, miễn là các dependency bên ngoài cũng tương thích. Nếu chương trình gọi API chỉ có ở Java 21, việc biên dịch với --release 17 sẽ báo lỗi thay vì âm thầm tạo ra ứng dụng không chạy được trên Java 17.

## 4. Các cải tiến ở tầng JVM vẫn có ý nghĩa

Java 9 không chỉ thay đổi ngôn ngữ và API. Một số cải tiến tác động đến cách JVM vận hành:

- **G1 trở thành garbage collector mặc định trên cấu hình server-class:** G1 chia heap thành các region và ưu tiên đạt mục tiêu thời gian tạm dừng có thể dự đoán hơn so với cách thu gom toàn heap truyền thống. G1 vẫn là lựa chọn mặc định trong nhiều môi trường JDK hiện đại; collector thực tế còn phụ thuộc cấu hình và mục tiêu vận hành.
- **Unified JVM Logging:** Cú pháp -Xlog thống nhất việc bật và định tuyến log từ nhiều thành phần JVM. Ví dụ -Xlog:gc* có thể bật log liên quan đến garbage collection. Cách này vẫn được dùng trong vận hành và chẩn đoán ứng dụng.
- **Compact Strings:** JVM có thể lưu String bằng biểu diễn nội bộ tiết kiệm bộ nhớ hơn đối với nội dung phù hợp. Đây là tối ưu implementation; chương trình vẫn sử dụng String theo Java API và không nên phụ thuộc vào cấu trúc nội bộ của nó.

Các thay đổi này không tạo ra cú pháp Java mới. Chúng ảnh hưởng đến hiệu năng, bộ nhớ và khả năng quan sát khi ứng dụng chạy.

Không nên mặc định một tối ưu JVM luôn làm ứng dụng nhanh hơn trong mọi tải công việc. Cần đo bằng dữ liệu thực tế, xem GC log, heap usage, latency và throughput trước khi thay đổi collector hoặc JVM flags.

## 5. Một ví dụ nối nhiều lớp với nhau

Ví dụ dưới đây kết hợp ba cải tiến có nguồn gốc từ Java 9:

1. Private method trong interface thuộc lớp ngôn ngữ.
2. List.of và Stream.takeWhile thuộc Java SE API.
3. javac --release thuộc công cụ JDK.

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

interface PricePolicy {
    int discount(int price);

    default int finalPrice(int price) {
        return applyDiscount(price, discount(price));
    }

    private int applyDiscount(int price, int discount) {
        return Math.max(0, price - discount);
    }
}

class StandardPricePolicy implements PricePolicy {
    @Override
    public int discount(int price) {
        return price / 10;
    }
}

public class PlatformExample {
    public static void main(String[] args) {
        List<String> layers = List.of("language", "libraries", "tools");
        List<Integer> prefix = Stream.of(1, 2, 3, 4)
                .takeWhile(number -> number < 3)
                .collect(Collectors.toList());
        PricePolicy policy = new StandardPricePolicy();

        System.out.println(layers);
        System.out.println(prefix);
        System.out.println(policy.finalPrice(1000));
    }
}
~~~

Lưu mã nguồn trong tệp PlatformExample.java. Dùng JDK 17 trở lên và chạy tại thư mục chứa tệp:

~~~bash
javac --release 17 -d out PlatformExample.java
java -cp out PlatformExample
~~~

Stdout chính xác:

~~~text
[language, libraries, tools]
[1, 2]
900
~~~

Giải thích theo từng lớp:

- javac phân tích interface, private method, kiểu dữ liệu và lời gọi API.
- List.of tạo collection không sửa được cấu trúc; Stream.takeWhile lấy phần đầu thỏa điều kiện.
- --release 17 bảo đảm mã nguồn chỉ dùng ngôn ngữ và API nền tảng thuộc Java 17.
- javac tạo bytecode trong thư mục out.
- java launcher khởi động JVM; JVM nạp class, kiểm tra bytecode và thực thi main.
- Khi chạy, JVM có thể JIT các đoạn mã phù hợp và quản lý bộ nhớ cho các object được tạo ra.

Ví dụ dùng cú pháp và API có từ Java 9, nhưng biên dịch theo mục tiêu Java 17 để minh họa cách một ứng dụng hiện đại chọn baseline hỗ trợ. JDK 24 đã được dùng để biên dịch và chạy ví dụ; stdout thu được khớp với kết quả trên.

## 6. Vai trò của Gradle/Maven trong mối quan hệ này

Gradle và Maven không thay thế javac hoặc JVM. Chúng tổ chức quy trình build và thường gọi công cụ JDK ở những bước tương ứng.

Một quy trình điển hình:

1. Build tool đọc cấu hình project, chọn JDK/toolchain và giải quyết dependency.
2. Tác vụ compile gọi javac với source level, release và classpath/module path phù hợp.
3. Tác vụ test khởi chạy test engine trên JVM.
4. Tác vụ package tạo JAR hoặc artifact khác, có thể bao gồm module descriptor.
5. Ứng dụng được chạy bằng java launcher trên JVM có phiên bản tương thích.

Cấu hình build có thể chọn một JDK để thực thi Gradle/Maven và một Java toolchain để biên dịch ứng dụng. Hai phiên bản này không nhất thiết phải giống nhau. Điều cần kiểm tra là compiler, API mục tiêu, class file và runtime deployment phải tương thích với nhau.

Với dự án modular, build tool còn phải đặt dependency đúng module path và giữ module descriptor trong artifact. Với ứng dụng không dùng JPMS, dependency thường được đưa vào classpath. Đây là lựa chọn kiến trúc và cấu hình của dự án, không phải mọi project Java đều bắt buộc dùng module path.

## 7. Các loại tương thích cần phân biệt

| Loại tương thích | Câu hỏi cần trả lời |
|---|---|
| Source compatibility | Mã nguồn có được compiler của phiên bản mục tiêu chấp nhận không? |
| API compatibility | Các API Java SE mà mã nguồn gọi có tồn tại trong phiên bản mục tiêu không? |
| Class file compatibility | JVM đích có hiểu phiên bản class file đã biên dịch không? |
| Runtime compatibility | Các dependency, module và dịch vụ cần thiết có sẵn khi chạy không? |
| Behavioral compatibility | Chương trình có giữ hành vi mong muốn trên runtime mới không? |

Một chương trình có thể biên dịch trên JDK mới nhưng thất bại trên runtime cũ do class file quá mới hoặc do gọi API không tồn tại. Dùng --release giúp kiểm soát source/API/class file cho Java SE mục tiêu, nhưng không tự bảo đảm mọi thư viện bên ngoài đều tương thích. Cần kiểm tra dependency và chạy test trên baseline runtime được hỗ trợ.

## 8. Cách phân loại một thay đổi Java

Khi đọc release note hoặc một đề xuất JEP, hãy xác định thay đổi nằm ở lớp nào:

| Dấu hiệu | Lớp thay đổi | Ảnh hưởng thường gặp |
|---|---|---|
| Có cú pháp, quy tắc kiểu hoặc cách khai báo mới | Ngôn ngữ | Cần compiler hỗ trợ; có thể ảnh hưởng source compatibility |
| Có lớp, method hoặc package API mới | Thư viện | Cần API có trong nền tảng mục tiêu và runtime |
| Có lệnh, tùy chọn javac/java hoặc công cụ mới | Công cụ JDK | Thay đổi quy trình phát triển, build, kiểm tra hoặc triển khai |
| Có thay đổi JIT, GC, class loading hoặc logging | JVM | Ảnh hưởng thực thi, hiệu năng, bộ nhớ hoặc chẩn đoán |
| Có thay đổi task, plugin hoặc cách giải quyết dependency | Công cụ build | Ảnh hưởng cấu hình và pipeline của project |

Một thay đổi có thể tác động nhiều lớp. JPMS là ví dụ rõ: module descriptor là cấu trúc mã nguồn do compiler xử lý; module system cung cấp quy tắc đọc và đóng gói; launcher/JVM phân giải mô-đun khi chạy; công cụ jar, jdeps và jlink hỗ trợ đóng gói, phân tích và tạo runtime image.

## 9. Checklist khi nâng cấp JDK

Khi chuyển ứng dụng sang JDK mới, hãy kiểm tra theo thứ tự:

1. **Baseline:** Xác định phiên bản Java thấp nhất mà sản phẩm phải hỗ trợ.
2. **Compiler:** Chọn toolchain và --release phù hợp; không chỉ đổi JDK cài trên máy phát triển.
3. **API:** Kiểm tra API Java SE và API bên thứ ba mà mã nguồn sử dụng.
4. **Dependencies:** Kiểm tra thư viện, plugin build, test engine và module descriptor.
5. **Runtime:** Chạy ứng dụng trên đúng loại runtime sẽ được triển khai; kiểm tra JVM flags và module path/classpath.
6. **Behavior:** Chạy test và đo hiệu năng, latency, throughput, bộ nhớ cùng log GC trên tải đại diện.
7. **Packaging:** Xác minh JAR, module descriptor và runtime image nếu ứng dụng phân phối runtime riêng.

Không nên kết luận nâng cấp thành công chỉ vì bước compile hoàn tất. Ứng dụng còn phải chạy được với dependency thật, runtime mục tiêu và cấu hình triển khai thực tế.

## 10. Kết luận

Một phiên bản Java là sự phối hợp của ngôn ngữ, Java SE API, công cụ JDK, công cụ build và JVM. Cải tiến ngôn ngữ quyết định mã nguồn có thể viết như thế nào; thư viện mở rộng khả năng chương trình; công cụ giúp biên dịch và đóng gói; JVM thực thi bytecode và quản lý tài nguyên khi chạy.

Các cải tiến Java 9 như private method trong interface, factory method cho collection, Stream.takeWhile, Flow API, JShell, jlink, jdeps, javac --release, unified logging và các cải tiến JVM vẫn có ứng dụng trong Java hiện đại. Khi đánh giá một tính năng, hãy phân loại đúng tầng của nó và kiểm tra khả năng tương thích từ compiler đến runtime.
