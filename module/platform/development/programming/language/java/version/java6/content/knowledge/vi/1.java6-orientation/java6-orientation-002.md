# Mối liên hệ giữa cấu trúc dữ liệu, công cụ biên dịch và tích hợp hệ thống

## 1. Ba nhóm kiến thức cùng phục vụ một chương trình

Một ứng dụng Java thường phải làm ba việc khác nhau: tổ chức dữ liệu để xử lý, biến mã nguồn thành chương trình chạy được, và trao đổi với môi trường bên ngoài. Cấu trúc dữ liệu, công cụ biên dịch và tích hợp hệ thống lần lượt giúp giải quyết ba nhu cầu đó.

Hãy hình dung một dịch vụ nhận hồ sơ, xếp loại theo điểm và ghi kết quả vào cơ sở dữ liệu:

- Cấu trúc dữ liệu biểu diễn hồ sơ đang chờ và các ngưỡng xếp loại trong bộ nhớ.
- Công cụ biên dịch kiểm tra mã Java, tạo tệp lớp và cung cấp điểm mở rộng cho công cụ phát triển.
- Phần tích hợp đọc hồ sơ từ nguồn ngoài, chuyển thành mô hình Java và ghi kết quả qua một hợp đồng phù hợp với hệ thống đích.

Ba nhóm này liên hệ qua mô hình dữ liệu và hợp đồng, nhưng hoạt động ở những giai đoạn khác nhau. Hiểu sự phân biệt ấy giúp đặt đúng câu hỏi khi thiết kế hoặc sửa lỗi: dữ liệu đang được tổ chức sai, mã chưa hợp lệ, hay việc trao đổi với hệ thống khác thất bại?

Trong ngữ cảnh chủ đề Java 6, bài dùng những nền tảng xuất hiện từ giai đoạn đó và vẫn có giá trị hiện nay, như `Deque`, `NavigableMap`, `JavaCompiler` và cơ chế xử lý annotation. Ví dụ chạy trên **JDK 17 trở lên**; không yêu cầu cài hay triển khai một môi trường Java 6.

## 2. Phân biệt luồng tạo chương trình và luồng dữ liệu

Có hai luồng cần nhìn riêng.

### Luồng tạo chương trình

```text
Mã nguồn Java + thư viện phụ thuộc + cấu hình công cụ
                       |
                       v
             Biên dịch / kiểm tra kiểu
                       |
                       v
                  Tệp .class
                       |
                       v
           Đóng gói và đưa vào môi trường chạy
```

Bộ biên dịch kiểm tra những điều có thể xác định từ mã nguồn và thông tin kiểu được cung cấp. Chẳng hạn, lời gọi một phương thức không tồn tại hoặc gán một `String` vào biến `int` bị phát hiện trước khi chạy.

Một quá trình xây dựng còn có thể chạy bộ xử lý annotation để kiểm tra mô hình hoặc sinh thêm mã. Việc kiểm tra, sinh mã và chạy ứng dụng là các hoạt động có đầu vào, đầu ra và thời điểm khác nhau. Một annotation không tự tạo hành vi: phải có công cụ hoặc mã thực thi đọc và xử lý nó.

### Luồng dữ liệu khi ứng dụng chạy

```text
Nguồn ngoài: tệp / yêu cầu mạng / cơ sở dữ liệu
                       |
                       v
     Bộ tiếp nhận: đọc, chuyển đổi, kiểm tra đầu vào
                       |
                       v
               Mô hình Java có kiểu
                       |
                       v
      Cấu trúc dữ liệu + thuật toán + quy tắc nghiệp vụ
                       |
                       v
     Bộ xuất: chuyển đổi và gửi kết quả ra bên ngoài
```

Dữ liệu bên ngoài chỉ xuất hiện khi chương trình chạy. Biên dịch thành công không chứng minh một hồ sơ vừa nhận có điểm hợp lệ, một dịch vụ từ xa đang hoạt động hay tài khoản cơ sở dữ liệu có quyền ghi.

Hai luồng gặp nhau tại **hợp đồng**. Mã nguồn định nghĩa kiểu dữ liệu và các thao tác được phép; phần tích hợp phải biến dữ liệu bên ngoài thành giá trị đáp ứng hợp đồng ấy trước khi lõi xử lý sử dụng.

## 3. Cấu trúc dữ liệu quyết định cách làm việc trong bộ nhớ

Một cấu trúc dữ liệu không chỉ là nơi chứa nhiều phần tử. Nó thể hiện những quan hệ và thao tác mà chương trình cần.

| Nhu cầu trong chương trình | Mô hình phù hợp để cân nhắc | Câu hỏi phải làm rõ |
| --- | --- | --- |
| Giữ các hồ sơ theo thứ tự tiếp nhận | Hàng đợi, có thể dùng `Deque` theo FIFO | Thêm và lấy ở đầu nào? |
| Tra cứu ngưỡng gần nhất không vượt quá điểm | `NavigableMap` với khóa được sắp thứ tự | Dùng ngưỡng bao gồm hay loại trừ điểm bằng nhau? |
| Tìm hồ sơ bằng mã định danh | `Map` | Gặp hai hồ sơ cùng mã thì thay thế hay báo lỗi? |
| Loại bỏ giá trị trùng | `Set` | Hai giá trị được coi là bằng nhau theo tiêu chí nào? |

FIFO là “vào trước, ra trước”. Với một `Deque`, thêm cuối bằng `addLast` rồi lấy đầu bằng `removeFirst` thể hiện chính sách đó. Nếu thay bằng cách thêm đầu và lấy đầu, chương trình chuyển sang cách xử lý vào sau ra trước. Cùng một kiểu chứa vẫn có thể tạo ra hành vi khác nếu cách dùng khác.

`NavigableMap` hỗ trợ truy vấn theo vị trí của khóa trong thứ tự. Ví dụ, `floorEntry(85)` tìm ánh xạ có khóa lớn nhất nhưng không lớn hơn 85. Nếu không có khóa thỏa điều kiện, phương thức trả `null`. Đây là phép tra cứu ngưỡng; nó không phải phép tìm khóa gần nhất theo khoảng cách tuyệt đối. [Tài liệu NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html)

Điểm quan trọng đối với tích hợp là **ý nghĩa của thứ tự**. Thứ tự các dòng được nhận về, thứ tự điểm tăng dần và thứ tự thời gian phát sinh sự kiện là ba quan hệ khác nhau. Chọn một collection không tự làm cho ba quan hệ ấy trùng nhau.

Ví dụ, đưa kết quả truy vấn vào hàng đợi chỉ giữ thứ tự mà nguồn đã cung cấp. Nếu cần thứ tự nghiệp vụ ổn định, hợp đồng nguồn phải định nghĩa thứ tự ấy hoặc chương trình phải chủ động sắp xếp.

Cũng cần phân biệt bộ nhớ với lưu trữ bền vững. Hàng đợi nằm trong tiến trình không tự giữ lại hồ sơ sau khi tiến trình dừng. Nếu yêu cầu không mất việc khi máy chủ gặp sự cố, cần thiết kế cơ chế lưu trữ hoặc hàng đợi bền vững ở ranh giới hệ thống.

## 4. Công cụ biên dịch tạo cầu nối từ mô hình mã đến chương trình

Trong cách sử dụng thông thường, người phát triển dùng `javac` trực tiếp hoặc thông qua công cụ xây dựng. Khi cần tích hợp chức năng biên dịch vào một công cụ Java, API `javax.tools.JavaCompiler` cung cấp giao diện gọi bộ biên dịch và nhận thông tin chẩn đoán. [Tài liệu JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html)

Mối liên hệ với cấu trúc dữ liệu thể hiện ở hai hướng:

1. Mã nguồn khai báo các kiểu như `Deque<Item>` hoặc `NavigableMap<Integer, String>`; bộ biên dịch kiểm tra việc sử dụng các kiểu ấy.
2. Công cụ phát triển có thể thu thập thông báo lỗi, mô hình phần tử hoặc kết quả phân tích vào các cấu trúc dữ liệu để lọc, sắp xếp và trình bày.

Đây không phải sự thay thế cho kiểm tra nghiệp vụ. `new Item("A", 150)` vẫn có thể đúng kiểu nếu hàm tạo nhận `int`; điều kiện “điểm phải từ 0 đến 100” cần được biểu diễn bằng kiểm tra phù hợp.

Xử lý annotation là một điểm giao tiếp khác. API `javax.annotation.processing` cho phép công cụ trao đổi với bộ xử lý annotation; các thành phần như `Filer` và `Messager` hỗ trợ tạo tệp và phát thông báo. Từ mô hình đã khai báo, một bộ xử lý cụ thể có thể sinh mã chuyển đổi hoặc kiểm tra quy ước, nếu được cấu hình tham gia quá trình xây dựng. Không nên suy ra mọi annotation đều được xử lý khi biên dịch hoặc đều có tác dụng khi chạy. [API xử lý annotation](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/package-summary.html)

Một số giới hạn cần nhớ:

- Mã sinh ra vẫn phải được kiểm tra và đóng gói như phần còn lại của chương trình.
- Kiểm tra kiểu không xác nhận độ tin cậy của một máy chủ bên ngoài.
- Việc cho phép người dùng gửi mã Java để biên dịch và chạy là một yêu cầu an toàn riêng. API biên dịch không cung cấp một môi trường cô lập an toàn cho mã không tin cậy.
- Bộ xử lý annotation là mã công cụ được thực thi trong quá trình xây dựng; cần quản lý nguồn và cấu hình của nó như các thành phần xây dựng khác.

### Có JVM chưa chắc có bộ biên dịch

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` khi môi trường không cung cấp bộ biên dịch. Vì vậy, một ứng dụng chỉ cần chạy mã đã biên dịch không nên bị buộc phải có công cụ biên dịch bên trong. Nếu chức năng thực sự cần API này, phải kiểm tra điều kiện môi trường và xử lý trường hợp thiếu công cụ. [Tài liệu ToolProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html)

Điều này giúp tách trách nhiệm triển khai: môi trường xây dựng cần những công cụ gì, còn môi trường chạy cần những thành phần gì? Không nên để một phép kiểm tra khả năng biên dịch vô tình trở thành điều kiện khởi động của mọi dịch vụ.

## 5. Tích hợp hệ thống nối hợp đồng Java với hợp đồng bên ngoài

Trong bài này, “bộ tiếp nhận” hoặc “bộ xuất” là phần mã làm cầu nối với nguồn hay đích bên ngoài. Có thể gọi chung chúng là bộ chuyển tiếp, tương ứng với ý tưởng adapter.

Ví dụ, lõi xử lý cần một danh sách hồ sơ:

```text
Hợp đồng trong Java:
    load() trả về các Item hợp lệ

Nguồn cụ thể có thể là:
    tệp dữ liệu
    cơ sở dữ liệu
    dịch vụ từ xa
    dữ liệu cố định phục vụ kiểm thử
```

Mỗi nguồn có quy tắc riêng về định dạng, mã hóa, quyền truy cập và lỗi. Bộ tiếp nhận chịu trách nhiệm xử lý các khác biệt ấy rồi cung cấp mô hình mà lõi hiểu được.

Đối với cơ sở dữ liệu, JDBC cung cấp API truy cập và xử lý dữ liệu, còn trình điều khiển cụ thể đảm nhiệm việc kết nối với nguồn tương ứng. Có API trong mã không đồng nghĩa đã có trình điều khiển phù hợp, địa chỉ đúng hoặc quyền truy cập hợp lệ. Khả năng hỗ trợ một chức năng cũng cần đối chiếu với trình điều khiển đang dùng. [Tổng quan java.sql](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/package-summary.html)

Ranh giới tích hợp nên trả lời ít nhất các câu hỏi sau:

| Khía cạnh | Ví dụ quyết định phải nêu rõ |
| --- | --- |
| Chuyển đổi | Chuỗi điểm không phải số được báo lỗi hay bỏ qua? |
| Tính hợp lệ | Điểm ngoài 0..100 được từ chối ở đâu? |
| Danh tính | Hai hồ sơ cùng mã là hai sự kiện hay một hồ sơ lặp? |
| Thứ tự | Nguồn bảo đảm thứ tự nào? |
| Lỗi | Mất kết nối làm thất bại cả lô hay chỉ một phần? |
| Tài nguyên | Ai đóng kết nối, luồng đọc và các đối tượng truy vấn? |
| Khối lượng | Đọc toàn bộ vào bộ nhớ hay xử lý theo từng phần? |

Cấu trúc dữ liệu của lõi nên phục vụ thao tác nghiệp vụ. Định dạng truyền bên ngoài nên phục vụ hợp đồng trao đổi. Không nên vô tình biến tên lớp triển khai như `TreeMap` thành một yêu cầu của giao thức.

Tương tự, một kiểu Java đúng không bảo đảm một lần ghi bên ngoài đã thành công. Nếu đã lấy một phần tử khỏi hàng đợi nhưng ghi cơ sở dữ liệu thất bại, chương trình phải có chính sách giữ lại, thử lại hoặc báo thất bại. Thay collection không tự giải quyết tính nguyên tử giữa thao tác trong bộ nhớ và thao tác ở hệ thống khác.

## 6. Ví dụ chạy được: tiếp nhận, tổ chức và phân loại hồ sơ

Chương trình sau dùng một nguồn dữ liệu cố định để có kết quả tái lập, không cần máy chủ hoặc cơ sở dữ liệu. Nguồn cố định đại diện cho hợp đồng tiếp nhận; đây chưa phải ví dụ kết nối mạng hay JDBC.

Các quyết định của ví dụ:

- Mỗi `Item` phải có mã khác rỗng và điểm trong 0..100.
- Các hồ sơ được xử lý theo thứ tự nguồn cung cấp.
- Các ngưỡng 0, 60 và 80 lần lượt bắt đầu nhóm BASIC, STANDARD và PRIORITY.
- Nhãn PRIORITY chỉ là kết quả phân loại, không thay đổi thứ tự xử lý.
- Cuối chương trình, một phép kiểm tra riêng cho biết bộ biên dịch có sẵn qua `ToolProvider` hay không.

Lưu tệp dưới tên `IntegrationMapDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.NavigableMap;
import java.util.TreeMap;
import javax.tools.ToolProvider;

public class IntegrationMapDemo {
    record Item(String id, int score) {
        Item {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException("score must be 0..100");
            }
        }
    }

    interface ItemSource {
        List<Item> load();
    }

    public static void main(String[] args) {
        ItemSource source = () -> List.of(
                new Item("A", 85),
                new Item("B", 40));

        NavigableMap<Integer, String> bands = new TreeMap<>();
        bands.put(0, "BASIC");
        bands.put(60, "STANDARD");
        bands.put(80, "PRIORITY");

        Deque<Item> pending = new ArrayDeque<>(source.load());
        while (!pending.isEmpty()) {
            Item item = pending.removeFirst();
            String band = bands.floorEntry(item.score()).getValue();
            System.out.println(item.id() + "=" + band);
        }

        boolean compilerAvailable =
                ToolProvider.getSystemJavaCompiler() != null;
        System.out.println("compilerAvailable=" + compilerAvailable);
    }
}
```

Dùng một JDK 17 trở lên, chạy từ thư mục chứa tệp:

```shell
javac --release 17 IntegrationMapDemo.java
java IntegrationMapDemo
```

Với một JDK đầy đủ có cung cấp bộ biên dịch cho `ToolProvider`, stdout là:

```text
A=PRIORITY
B=BASIC
compilerAvailable=true
```

Nếu chạy tệp lớp trong một môi trường không cung cấp bộ biên dịch qua API này, dòng cuối có thể là `compilerAvailable=false`. Hai dòng phân loại vẫn có cùng ý nghĩa; chương trình không gọi biên dịch động.

### Đọc kết quả theo ba vai trò

**Cấu trúc dữ liệu:** `ArrayDeque` được tạo từ danh sách nguồn nên giữ thứ tự duyệt A rồi B. `removeFirst()` lấy từng phần tử ở đầu. Kiểm tra `isEmpty()` trước khi lấy giúp vòng lặp không gọi thao tác lấy đầu trên hàng đợi rỗng.

`TreeMap` giữ các khóa ngưỡng theo thứ tự số. Với điểm 85, `floorEntry` chọn khóa 80; với điểm 40, nó chọn khóa 0. Vì điểm đã được kiểm tra không âm và bảng luôn có ngưỡng 0, kết quả tra cứu trong ví dụ không phải `null`.

**Công cụ biên dịch:** lệnh `javac` kiểm tra và tạo mã chạy cho toàn bộ ví dụ. `--release 17` đặt mức ngôn ngữ, định dạng tệp lớp và tập API nền tảng tương ứng cho lần biên dịch này; nó không tự cài thư viện ngoài hay xác minh dữ liệu nghiệp vụ. Phép gọi `ToolProvider` trong `main` chỉ kiểm tra sự hiện diện của công cụ, không thực hiện thêm một lần biên dịch. [Tài liệu lệnh javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)

**Tích hợp:** `ItemSource` là hợp đồng tiếp nhận. Lõi cần `List<Item>`, không cần biết hồ sơ được đọc bằng cách nào. Nguồn cố định giúp kiểm tra thuật toán mà không bị phụ thuộc vào kết nối ngoài. Khi thay nguồn, vẫn phải giữ nguyên các cam kết về tính hợp lệ, thứ tự và ý nghĩa của dữ liệu.

Hàm tạo của `Item` cho thấy một ràng buộc nghiệp vụ được kiểm tra khi tạo đối tượng. Nó chưa chứng minh mã là duy nhất trên toàn bộ tập hồ sơ; điều kiện duy nhất, nếu cần, đòi hỏi kiểm tra trên tập dữ liệu hoặc tại nơi lưu trữ.

### Những bảo đảm ví dụ chưa cung cấp

Ví dụ không giới hạn số hồ sơ, không lưu hàng đợi bền vững và không có xử lý đồng thời. `ArrayDeque` cấm phần tử `null` và không tự bảo đảm an toàn khi nhiều luồng cùng truy cập. Những điều kiện đó phải được tính đến khi thay nguồn cố định bằng nguồn thật. [Tài liệu ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html)

Nếu số hồ sơ có thể rất lớn, hợp đồng `load()` trả toàn bộ một `List` có thể không phù hợp. Khi ấy cần thiết kế đọc từng phần, giới hạn dữ liệu đang chờ và quản lý thời gian sống của tài nguyên. Đây là thay đổi hợp đồng tích hợp, không chỉ là thay một lớp collection.

## 7. Đặt đúng nơi kiểm tra và xử lý lỗi

Một cách thực hành tốt là gắn mỗi phép kiểm tra với thông tin mà nó thực sự có.

| Tình huống | Nơi có thông tin để xử lý | Vì sao |
| --- | --- | --- |
| Gọi phương thức không tồn tại trên `Item` | Bộ biên dịch | Kiểu và chữ ký phương thức đã có trong mã |
| Dòng nhập có điểm là `"abc"` | Bộ tiếp nhận | Phải đọc dữ liệu thực tế mới biết chuyển đổi thất bại |
| Điểm số là 150 | Kiểm tra mô hình hoặc quy tắc nghiệp vụ | Đây là ràng buộc giá trị, không chỉ ràng buộc kiểu `int` |
| Hai hồ sơ cùng mã | Thành phần có phạm vi dữ liệu thích hợp | Một đối tượng riêng lẻ không thấy toàn bộ danh tính |
| Không tìm thấy ngưỡng | Phần quản lý cấu hình và phân loại | Phụ thuộc nội dung bảng và miền giá trị đầu vào |
| Kết nối cơ sở dữ liệu bị ngắt | Phần tích hợp và chính sách của ca sử dụng | Cần biết tác vụ nào đã hoàn thành và có thể thử lại hay không |

Đặc biệt, thử lại không chỉ có nghĩa “đưa phần tử vào hàng đợi lần nữa”. Nếu hệ thống đích đã ghi thành công nhưng phản hồi bị mất, gửi lại có thể tạo kết quả trùng. Cần hợp đồng nhận diện yêu cầu hoặc một chính sách xử lý trùng rõ ràng. Không thể suy ra bảo đảm “đúng một lần” từ một collection cục bộ.

Khi chẩn đoán, nên giữ thông tin lỗi theo đúng ngữ cảnh: mã hồ sơ, bước đang thực hiện, lỗi đầu vào hay lỗi kết nối, và hành động đã hoàn thành. Không ghi thông tin bí mật của kết nối vào thông báo cho người dùng.

## 8. Các nhầm lẫn thường gặp

### “Đã biên dịch thì dữ liệu đã được kiểm tra”

Biên dịch xác nhận một phần tính hợp lệ của chương trình theo quy tắc ngôn ngữ và kiểu. Dữ liệu đến sau thời điểm biên dịch vẫn phải được chuyển đổi, kiểm tra và xử lý lỗi.

Trong ví dụ, kiểu `int` cho phép nhiều giá trị ngoài 0..100. Chính hàm tạo mới thực thi điều kiện của miền bài toán.

### “Có hàng đợi trong bộ nhớ thì đã có hệ thống hàng đợi”

Một cấu trúc dữ liệu cục bộ giúp tổ chức việc xử lý bên trong một tiến trình. Hệ thống hàng đợi bền vững còn phải giải quyết lưu trữ, xác nhận xử lý, phục hồi và nhiều bên tham gia. Đó là các hợp đồng bổ sung.

### “Dùng generics thì dữ liệu bên ngoài chắc chắn đúng”

`List<Item>` giúp kiểm tra cách dùng danh sách trong mã có kiểu. Nó không tự biến một chuỗi JSON hoặc một dòng tệp bất kỳ thành `Item` hợp lệ. Phần chuyển đổi và ràng buộc giá trị vẫn cần thiết.

### “Annotation luôn được đọc bằng phản chiếu khi chạy”

Một công cụ có thể xử lý annotation khi xây dựng; một thành phần khác có thể đọc metadata khi chạy nếu annotation và cơ chế sử dụng cho phép. Cần xác định ai đọc, đọc lúc nào và tạo hiệu ứng gì. Không nên coi hai cơ chế là một.

### “Mọi JVM đều có thể gọi bộ biên dịch”

Khả năng chạy tệp lớp và khả năng cung cấp bộ biên dịch qua API là hai điều kiện riêng. Hãy kiểm tra môi trường thực tế thay vì bỏ qua trường hợp `ToolProvider` trả `null`.

## 9. Thực hành để củng cố mối liên hệ

### Bài 1: Kiểm tra ranh giới ngưỡng

Thay hai hồ sơ bằng bốn hồ sơ có điểm 59, 60, 79 và 80. Dự đoán nhãn trước khi chạy.

Kết quả phân loại phải lần lượt là BASIC, STANDARD, STANDARD và PRIORITY. Điểm đúng bằng ngưỡng thuộc nhóm bắt đầu tại ngưỡng ấy vì dùng `floorEntry`.

### Bài 2: Phân biệt thứ tự và phân loại

Đảo thứ tự A và B trong danh sách nguồn mà không đổi điểm.

B sẽ được in trước A, nhưng B vẫn là BASIC và A vẫn là PRIORITY. Điều này chứng minh hàng đợi quyết định thứ tự xử lý, còn bảng ngưỡng quyết định nhãn.

### Bài 3: Xác định giai đoạn phát hiện lỗi

Thử thay `new Item("A", 85)` thành `new Item("A", 150)`.

Chương trình vẫn đúng về kiểu ở biểu thức khởi tạo, nhưng ném `IllegalArgumentException` khi thực thi hàm tạo. Nguồn được tạo trong `load()` và thất bại trước khi vòng lặp phân loại bắt đầu.

Tiếp theo, đổi lời gọi `item.score()` thành `item.unknownScore()`. Lỗi này bị bộ biên dịch phát hiện vì `Item` không khai báo phương thức đó.

### Bài 4: Thiết kế nguồn thật trên giấy

Giả sử thay nguồn cố định bằng dữ liệu từ cơ sở dữ liệu. Trước khi viết mã kết nối, hãy mô tả:

1. Những cột nào tạo thành một `Item` và cách xử lý giá trị thiếu.
2. Thứ tự hồ sơ mà nguồn trả về.
3. Ai đóng tài nguyên sau khi đọc.
4. Làm gì khi đọc thành công một phần rồi gặp lỗi.
5. Có cần nạp toàn bộ danh sách hay phải đọc từng lô.

Câu trả lời tốt phải tách được quy tắc của mô hình, cách tổ chức dữ liệu trong bộ nhớ và trách nhiệm của phần kết nối. Việc đổi nguồn không nên làm thay đổi ngầm ý nghĩa của điểm, mã hồ sơ hoặc các ngưỡng xếp loại.

Sau những bài tập này, hãy tự diễn đạt đường đi của một hồ sơ: nó được đọc và kiểm tra ở đâu, được giữ và tra cứu bằng cấu trúc nào, phần nào đã được bộ biên dịch kiểm tra, và điều gì chỉ có thể xác nhận khi chạy. Đó là nền tảng để học sâu từng nhóm API mà vẫn giữ được bức tranh của toàn chương trình.
