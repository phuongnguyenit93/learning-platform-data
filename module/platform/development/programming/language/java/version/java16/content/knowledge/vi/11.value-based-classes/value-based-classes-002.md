# Nhận diện value-based class qua hợp đồng API của wrapper, Optional và java.time

Trong Java hiện đại, nhiều lớp thư viện được thiết kế để biểu diễn **giá trị** thay vì một thực thể cần được nhận diện bằng danh tính object. Các ví dụ quen thuộc gồm những lớp wrapper như **Integer**, các lớp **Optional** và những kiểu ngày giờ trong **java.time**. Những lớp này được gọi là *value-based class*.

Điều cần học không chỉ là ghi nhớ tên lớp. Lập trình viên cần biết cách đọc hợp đồng API để xác định một lớp có phải value-based hay không, hiểu vì sao hai instance bằng nhau có thể thay thế cho nhau và lựa chọn phép so sánh phù hợp. Bài học này tập trung vào hợp đồng vẫn được duy trì trong Java hiện đại, lấy tài liệu Java SE 27 làm mốc đối chiếu.

## 1. Cách nhận diện value-based class trong Java API

Cách đáng tin cậy nhất là đọc tài liệu API của chính lớp đó. Trong phần mô tả lớp, JavaDoc thường ghi rõ:

> This is a value-based class.

Ngay sau đó, tài liệu nhắc rằng các instance bằng nhau theo **equals()** phải được xem là có thể thay thế cho nhau; không sử dụng chúng để đồng bộ hóa và cần dùng **equals()** để so sánh. Liên kết *value-based* trong JavaDoc dẫn tới tài liệu giải thích hợp đồng chung của nhóm lớp này.

Theo tài liệu Value-based Classes của Java SE, hợp đồng có các đặc điểm chính:

- Lớp chỉ khai báo các instance field là **final**. Những field này vẫn có thể tham chiếu tới object mutable, nên không thể suy ra mọi value-based class đều bất biến sâu.
- **equals()**, **hashCode()** và **toString()** được tính từ giá trị các field và các object mà chúng tham chiếu, không dựa trên identity của instance.
- Khi hai instance bằng nhau theo **equals()**, các phương thức của lớp xem chúng có thể thay thế cho nhau mà không làm thay đổi hành vi quan sát được.
- Lớp không dùng intrinsic monitor của instance để đồng bộ.
- Lớp không cam kết mỗi lần gọi cơ chế tạo instance sẽ nhận một identity duy nhất. Factory method có thể trả về cùng một tham chiếu cho những lần tạo ra các giá trị bằng nhau.
- Lớp là **final** và có cấu trúc kế thừa phù hợp với hợp đồng value-based.

Các đặc điểm này giúp giải thích bản chất của nhóm lớp, nhưng không nên dùng chúng như một phép thử tự suy đoán. Một lớp có field **final**, có **equals()** hoặc bất biến chưa chắc đã được công bố là value-based. Hãy tìm tuyên bố rõ ràng trong JavaDoc của lớp hoặc tài liệu API chính thức.

## 2. Nhận diện các lớp wrapper trong java.lang

Tám lớp wrapper tương ứng với tám kiểu nguyên thủy có giá trị là:

| Kiểu nguyên thủy | Lớp wrapper |
| --- | --- |
| **byte** | **Byte** |
| **short** | **Short** |
| **int** | **Integer** |
| **long** | **Long** |
| **float** | **Float** |
| **double** | **Double** |
| **char** | **Character** |
| **boolean** | **Boolean** |

Tài liệu Java SE hiện hành đánh dấu các lớp wrapper này là value-based. Ví dụ, JavaDoc của **Integer** mô tả đây là wrapper của kiểu **int**, sau đó ghi rõ đây là value-based class và yêu cầu xem các instance bằng nhau là có thể thay thế cho nhau. **Byte**, **Long**, **Double**, **Boolean** và các wrapper còn lại có cùng nguyên tắc trong hợp đồng API.

Điều này có ý nghĩa thực tế khi so sánh:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // Không được dựa vào kết quả này
~~~

Hai biến biểu diễn cùng giá trị số, vì vậy **equals()** là phép so sánh phù hợp. Kết quả của **==** với hai reference phản ánh việc chúng có trỏ tới cùng một object hay không. Hợp đồng value-based không bảo đảm factory phải trả về một instance mới hoặc phải tái sử dụng instance cũ.

Cần phân biệt trường hợp so sánh reference với trường hợp so sánh primitive. Khi một toán hạng là primitive, Java có thể unbox wrapper trước khi thực hiện phép so sánh:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

boolean sameReference = first == second;
boolean sameNumber = first.intValue() == second.intValue();
boolean sameValue = first.equals(second);
~~~

- **sameReference** kiểm tra identity của hai reference và không phù hợp để kiểm tra giá trị của value-based class.
- **sameNumber** so sánh hai giá trị primitive sau khi unbox.
- **sameValue** so sánh theo hợp đồng **equals()** của wrapper.

Trong code thông thường, hãy ưu tiên kiểu primitive khi chỉ cần lưu và tính toán giá trị số; dùng wrapper khi cần biểu diễn giá trị có thể vắng mặt, làm việc với generic hoặc sử dụng API yêu cầu object.

### Tạo wrapper theo cách hiện hành

Không dùng constructor như **new Integer(42)** hoặc **new Boolean(true)**. Các constructor tạo instance trực tiếp của wrapper đã deprecated và không còn là cách tạo object được khuyến nghị. Dùng autoboxing, **valueOf()** hoặc phương thức parse phù hợp:

~~~java
Integer count = 42;                   // Autoboxing
Integer parsed = Integer.valueOf("42");
int primitive = Integer.parseInt("42");
~~~

Cách viết này phù hợp với API hiện hành và tránh tạo giả định về identity của wrapper.

## 3. Nhận diện Optional và các lớp Optional cho primitive

**Optional<T>** là một container có thể chứa một giá trị khác null hoặc biểu diễn trạng thái không có kết quả. JavaDoc của lớp ghi rõ đây là value-based class. Hợp đồng này cũng áp dụng cho các lớp chuyên biệt:

- **OptionalInt** chứa một giá trị **int** hoặc trạng thái rỗng.
- **OptionalLong** chứa một giá trị **long** hoặc trạng thái rỗng.
- **OptionalDouble** chứa một giá trị **double** hoặc trạng thái rỗng.

JavaDoc của cả ba lớp Optional chuyên biệt cũng ghi rõ chúng là value-based class. Do đó, không dùng identity của các container này để quyết định chúng có biểu diễn cùng một kết quả hay không.

Ví dụ:

~~~java
Optional<String> first = Optional.of("Java");
Optional<String> second = Optional.of(new String("Java"));

System.out.println(first.equals(second)); // true
~~~

Hai Optional bằng nhau vì cả hai đều chứa một giá trị **String** bằng nhau theo **String.equals()**. Việc một Optional đang rỗng hay có giá trị cũng thuộc trạng thái giá trị của container:

~~~java
Optional<String> noName1 = Optional.empty();
Optional<String> noName2 = Optional.empty();

System.out.println(noName1.equals(noName2)); // true
~~~

Không kiểm tra hai Optional bằng **==**, kể cả khi chúng được tạo bằng **empty()**. API không hứa hẹn identity của kết quả factory.

Một số phương thức hiện hành thường dùng:

~~~java
import java.util.Optional;
import java.util.OptionalInt;

String rawName = null;
Optional<String> name = Optional.ofNullable(rawName);

String displayName = name.orElse("Khách");
name.ifPresent(System.out::println);

Optional<Integer> age = Optional.of(20);
OptionalInt count = OptionalInt.of(3);
~~~

**Optional** chủ yếu được thiết kế làm kiểu trả về của phương thức khi cần biểu diễn rõ ràng trường hợp không có kết quả. Một biến có kiểu Optional nên luôn tham chiếu tới một Optional object; không gán chính biến đó thành **null**. Bên trong Optional, giá trị được chứa có thể là một object khác; tính value-based của container không tự làm object được chứa trở thành bất biến.

## 4. Nhận diện các kiểu giá trị trong java.time

API **java.time** cung cấp các kiểu biểu diễn ngày, giờ, thời điểm và khoảng thời gian. Nhiều lớp cốt lõi trong package này được JavaDoc công bố là value-based class. Có thể nhận diện qua các ví dụ phổ biến sau:

| Lớp | Giá trị được biểu diễn | Ghi chú |
| --- | --- | --- |
| **LocalDate** | Ngày theo lịch ISO, không có giờ và múi giờ | Phù hợp biểu diễn ngày sinh hoặc ngày nghiệp vụ |
| **LocalTime** | Giờ địa phương, không có ngày và múi giờ | Chỉ biểu diễn phần giờ |
| **LocalDateTime** | Ngày và giờ địa phương, không có múi giờ | Chưa xác định được một instant nếu thiếu offset hoặc zone |
| **Instant** | Một điểm trên dòng thời gian | Thường dùng làm timestamp |
| **OffsetDateTime** | Ngày giờ cùng UTC offset | Có thể xác định instant |
| **ZonedDateTime** | Ngày giờ cùng múi giờ | Mang quy tắc của ZoneId |
| **Duration** | Khoảng thời gian theo giây và nano giây | Phù hợp đo thời lượng |
| **Period** | Khoảng thời gian theo năm, tháng và ngày | Phù hợp phép tính theo lịch |

Đây là các ví dụ tiêu biểu, không phải quy tắc rằng mọi lớp trong **java.time** đều mặc nhiên value-based. Khi làm việc với một kiểu khác trong package này, hãy kiểm tra JavaDoc của chính lớp đó.

Ví dụ, JavaDoc của **LocalDate**, **LocalDateTime**, **Instant**, **Duration**, **Period**, **OffsetDateTime** và **ZonedDateTime** đều có tuyên bố value-based. Những lớp này cũng được mô tả là immutable và thread-safe. Vì trạng thái của chúng biểu diễn ngày giờ hoặc khoảng thời gian, các instance có cùng giá trị có thể được thay thế cho nhau trong phép tính theo hợp đồng API.

~~~java
import java.time.LocalDate;

LocalDate fromFactory = LocalDate.of(2026, 11, 27);
LocalDate fromText = LocalDate.parse("2026-11-27");

System.out.println(fromFactory.equals(fromText)); // true
~~~

Hai cách tạo tạo ra cùng ngày theo lịch. Hãy dùng **equals()** để so sánh ngày. Không dùng **==** để xác định chúng có cùng ngày hay không.

### Chọn đúng kiểu ngày giờ theo ý nghĩa dữ liệu

Việc nhận diện value-based class cũng giúp đọc đúng mô hình dữ liệu:

- Dùng **LocalDate** cho ngày lịch, ví dụ ngày sinh hoặc ngày hóa đơn.
- Dùng **LocalDateTime** cho ngày giờ địa phương khi ngữ cảnh đã xác định múi giờ ở nơi khác.
- Dùng **Instant** để lưu một thời điểm tuyệt đối, ví dụ thời điểm ghi nhận sự kiện.
- Dùng **OffsetDateTime** khi cần lưu ngày giờ cùng độ lệch UTC.
- Dùng **ZonedDateTime** khi cần áp dụng quy tắc múi giờ như **Asia/Ho_Chi_Minh** hoặc **Europe/Paris**.
- Dùng **Duration** cho lượng thời gian tính theo giây và nano giây; dùng **Period** cho lượng thời gian theo năm, tháng và ngày.

Ví dụ sau minh họa sự khác nhau giữa thời điểm và ngày giờ địa phương:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

Instant eventTime = Instant.parse("2026-11-27T03:00:00Z");

LocalDateTime localTime = LocalDateTime.ofInstant(
    eventTime,
    ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

**Instant** biểu diễn điểm trên dòng thời gian; **LocalDateTime** biểu diễn cách đọc ngày giờ trên đồng hồ địa phương. Cả hai đều là kiểu value-based, nhưng mang ý nghĩa nghiệp vụ khác nhau. Hãy chọn kiểu dựa trên dữ liệu cần biểu diễn, sau đó so sánh theo hợp đồng giá trị của kiểu đó.

## 5. Quy trình kiểm tra một lớp có phải value-based class hay không

Khi gặp một lớp thư viện chưa quen, có thể kiểm tra theo quy trình sau:

1. Mở JavaDoc của lớp trong đúng phiên bản Java mà dự án sử dụng.
2. Đọc phần mô tả lớp và tìm câu tuyên bố **This is a value-based class** hoặc liên kết tới tài liệu Value-based Classes.
3. Đọc mô tả **equals()** và **hashCode()** để hiểu trạng thái nào quyết định hai instance bằng nhau.
4. Kiểm tra API tạo instance có cam kết identity duy nhất hay không. Với value-based class, không được giả định factory luôn tạo object mới.
5. Kiểm tra các khuyến cáo về đồng bộ hóa và thao tác nhạy cảm với identity.
6. Chọn cách sử dụng dựa trên giá trị mà lớp biểu diễn: so sánh bằng **equals()**, dùng **hashCode()** theo hợp đồng, và tránh logic phụ thuộc identity.

Không phân loại một lớp chỉ vì nó **final**, immutable hoặc có factory method. Đó là các dấu hiệu thường gặp trong thiết kế value-based, nhưng tuyên bố trong tài liệu API mới là căn cứ cần kiểm tra.

## 6. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Lớp immutable nào cũng là value-based class | Immutable và value-based là hai đặc điểm khác nhau; cần kiểm tra JavaDoc |
| Gọi factory hai lần chắc chắn nhận hai object khác nhau | Factory của value-based class không cam kết identity duy nhất |
| Gọi factory hai lần chắc chắn nhận cùng object | API cũng không cam kết phải tái sử dụng cùng instance |
| Optional chỉ có một lớp value-based | Optional, OptionalInt, OptionalLong và OptionalDouble đều có hợp đồng value-based |
| Mọi lớp trong java.time đều tự động value-based | Kiểm tra tuyên bố trong JavaDoc của từng lớp |
| Instance immutable có thể dùng làm monitor an toàn | Bất biến không bảo đảm quyền sở hữu độc quyền monitor; không đồng bộ trên value-based instance |

## 7. Kết luận

Để nhận diện value-based class, hãy đọc tuyên bố và hợp đồng trong JavaDoc của lớp. Các lớp wrapper của kiểu nguyên thủy, **Optional** cùng các biến thể Optional cho primitive, và nhiều kiểu cốt lõi trong **java.time** đều là ví dụ đang được Java SE công bố rõ ràng.

Hợp đồng này cho phép chương trình làm việc dựa trên giá trị và xem các instance bằng nhau là có thể thay thế cho nhau. Vì vậy, hãy dùng **equals()** để so sánh, **hashCode()** theo hợp đồng giá trị, chọn đúng kiểu dữ liệu cho ý nghĩa nghiệp vụ và tránh phụ thuộc vào identity của instance.

## Tài liệu tham khảo

- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [Integer — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Integer.html)
- [Optional — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Optional.html)
- [OptionalInt — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalInt.html)
- [OptionalLong — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalLong.html)
- [OptionalDouble — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalDouble.html)
- [LocalDate — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDate.html)
- [LocalTime — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalTime.html)
- [LocalDateTime — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDateTime.html)
- [Instant — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html)
- [Duration — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Duration.html)
- [Period — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Period.html)
- [OffsetDateTime — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/OffsetDateTime.html)
- [ZonedDateTime — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html)

