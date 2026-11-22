# So sánh giá trị và giới hạn sử dụng danh tính đối tượng trong java.time (Java 8+)

## 1. Vì sao ngày giờ phải được so sánh theo giá trị?

Hai đối tượng Java có thể biểu diễn **cùng một ngày**, **cùng một thời điểm thực trên dòng thời gian**, hoặc **cùng các trường ngày–giờ địa phương** mà không phải cùng một đối tượng trong bộ nhớ. Bởi vậy, với API **java.time** của Java 8+, câu hỏi đúng không phải luôn là "hai tham chiếu có trỏ tới cùng object không?", mà là **"theo nghiệp vụ, hai giá trị này có bằng nhau không?"**

Ví dụ: hai đối tượng **LocalDate** độc lập đều mang ngày 01/02/2025; hai đối tượng **OffsetDateTime** biểu diễn 08:00 tại UTC+07:00 và 01:00 tại UTC; hoặc hai **ZonedDateTime** cùng Instant nhưng khác vùng thời gian. Những tình huống đó yêu cầu cách so sánh khác nhau.

**Mục tiêu học tập:**

1. Hiểu **value-based class** và vì sao không dựa vào danh tính đối tượng.
2. Phân biệt **==**, **equals**, **hashCode**, **compareTo**, **isBefore/isAfter/isEqual** và so sánh qua **Instant**.
3. Hiểu sự khác nhau giữa **giá trị ngày địa phương**, **giá trị ngày–giờ có offset/zone** và **cùng một thời điểm thực**.
4. Dùng java.time an toàn làm khóa Map/Set, lựa chọn comparator cho TreeSet/TreeMap đúng ý định.
5. Tránh **synchronized trên value-based object**, **System.identityHashCode**, **IdentityHashMap** hoặc suy luận dựa trên caching.
6. Kiểm chứng bằng mã Java 17 chạy độc lập, đầu ra xác định và các tình huống dễ nhầm.

Các lớp **LocalDate**, **LocalDateTime**, **Instant**, **OffsetDateTime**, **ZonedDateTime**, **Duration**, **Period** vẫn được Java SE hiện đại hỗ trợ. Bài tập trung vào API còn áp dụng; phần lớn phép toán đã có từ Java 8.

## 2. Khái niệm value-based class: giá trị quan trọng hơn danh tính

Tài liệu Java gọi nhiều lớp biểu diễn ngày giờ là **value-based classes**. Đặc điểm quan trọng là:

- Đối tượng mô tả một **giá trị** bằng các trường dữ liệu của nó.
- Những instance mà **equals** coi là bằng nhau cần được ứng dụng xem là có thể **thay thế cho nhau** khi thực hiện các phương thức của kiểu đó.
- Không có hợp đồng bảo đảm mỗi lời gọi **of(...)**, **parse(...)**, **plusDays(...)** hoặc một factory tương tự sẽ luôn cấp phát một object có **danh tính tham chiếu mới**.
- Ngược lại, cũng không có hợp đồng bảo đảm hai giá trị bằng nhau sẽ luôn dùng chung một tham chiếu.
- Các kiểu giá trị ngày giờ chính thường **immutable** và **thread-safe**: thao tác tính toán trả một giá trị mới về mặt ngữ nghĩa, không sửa các trường của giá trị cũ.

Ví dụ:

~~~java
LocalDate first = LocalDate.of(2025, 2, 1);
LocalDate second = LocalDate.parse("2025-02-01");

System.out.println(first.equals(second)); // true
~~~

**Không kết luận về first == second.** Hai biểu thức factory/parse có thể trả các tham chiếu khác nhau hoặc được runtime tái sử dụng; điều cần kiểm tra là cùng giá trị ngày.

### Có phải đối tượng immutable chắc chắn là value-based?

**Không nên đồng nhất hai khái niệm.** Immutable nói rằng trạng thái không bị sửa sau khi tạo; value-based còn đặt ra những hạn chế ngữ nghĩa liên quan tới **object identity**. Khi tài liệu lớp java.time ghi rõ là value-based, phải tuân thủ giới hạn tương ứng.

**Không phải mọi thứ trong java.time đều là một "giá trị thời điểm".** Ví dụ **Clock** là nguồn cung cấp thời gian cho code, còn **LocalDate** là ngày lịch; ý nghĩa so sánh phụ thuộc loại và contract, không thể áp dụng một quy tắc cho mọi kiểu mà không đọc API.

## 3. == và equals: hai câu hỏi khác nhau

Với hai biến tham chiếu của một class:

| Biểu thức | Câu hỏi thực chất |
| --- | --- |
| **a == b** | Hai tham chiếu có chỉ cùng một object không? |
| **a.equals(b)** | Theo hợp đồng của lớp, hai đối tượng có cùng **giá trị** không? |
| **Objects.equals(a, b)** | Hai giá trị có bằng nhau không, đồng thời xử lý trường hợp null an toàn? |
| **a.hashCode()** | Mã băm tương thích với equals, dùng trong HashMap/HashSet; không phải object identity |
| **a.compareTo(b)** | Quan hệ thứ tự mà lớp định nghĩa; không nhất thiết là so sánh Instant trong mọi kiểu |
| **a.isEqual(b)** | Một phép so sánh được kiểu ngày giờ cụ thể định nghĩa; ý nghĩa khác nhau theo lớp |

Với **LocalDate**, biểu thức:

~~~java
LocalDate a = LocalDate.of(2025, 2, 1);
LocalDate b = LocalDate.parse("2025-02-01");

boolean sameDate = a.equals(b);        // true
boolean sameOrder = a.compareTo(b) == 0; // true
~~~

**==** chỉ kiểm tra identity và không phải cách đáng tin để kiểm tra hai ngày bằng nhau. Việc test với vài phiên bản JDK thấy **a == b** có thể đúng hay sai không tạo ra một quy tắc chung.

### Tại sao caching không phải một phần của logic nghiệp vụ?

Một implementation có thể cache instance, tái dùng giá trị singleton hoặc cấp phát object mới. Những tối ưu ấy không làm thay đổi kết quả **equals**. Dựa vào chúng để nhận diện "ngày này đã có chưa" sẽ làm code phụ thuộc JVM, cách tạo đối tượng và tối ưu hóa.

**Quy tắc:** dùng **equals/Objects.equals** cho bình đẳng giá trị; dùng các phép so sánh thời gian tương ứng khi mục tiêu là thứ tự hoặc cùng mốc thời gian.

## 4. LocalDate, LocalTime và LocalDateTime: so sánh trường lịch địa phương

### LocalDate là một ngày, không phải một Instant

~~~java
LocalDate d1 = LocalDate.of(2025, 2, 1);
LocalDate d2 = LocalDate.parse("2025-02-01");
LocalDate tomorrow = d1.plusDays(1);

System.out.println(d1.equals(d2));      // true
System.out.println(d1.isBefore(tomorrow)); // true
~~~

**LocalDate** lưu ngày theo lịch ISO, không chứa giờ hay vùng thời gian. **equals** so ngày được biểu diễn; **isBefore/isAfter** so thứ tự trên trục ngày của lịch. **isEqual** của LocalDate có ích đặc biệt khi so với **ChronoLocalDate** của hệ lịch khác nhưng cùng ngày theo epoch day; phần 13 trình bày trường hợp này.

Không thể đổi **LocalDate** sang một mốc Instant chính xác chỉ bằng chính đối tượng đó. Cần thêm thời gian trong ngày và offset/ZoneId theo nghiệp vụ; những múi giờ khác nhau có thể cho Instant khác nhau.

### LocalTime là thời gian trong một ngày, không có ngày

~~~java
LocalTime a = LocalTime.of(9, 30);
LocalTime b = LocalTime.parse("09:30");
boolean sameTime = a.equals(b); // true
~~~

**LocalTime** mô tả giờ–phút–giây–nano trong ngày. Không có ngày, offset hay time zone. So sánh **LocalTime** không tự nói sự kiện nào xảy ra trước trên một dòng thời gian toàn cầu: 09:30 ở hai múi giờ hoặc ở hai ngày khác nhau có thể là những thời điểm khác nhau.

### LocalDateTime là ngày và giờ "trên đồng hồ"

~~~java
LocalDateTime a = LocalDateTime.of(2025, 1, 1, 12, 0);
LocalDateTime b = LocalDateTime.parse("2025-01-01T12:00");
boolean sameLocalFields = a.equals(b); // true
~~~

**LocalDateTime** không có offset/zone, nên hai giá trị bằng nhau theo các trường local **không tự xác định** hai sự kiện có cùng Instant. Khi cần đối chiếu sự kiện trên toàn cầu, trước hết phải biết vùng thời gian/offset được áp dụng và chuyển về Instant.

**Đừng chỉ so chuỗi định dạng** để kiểm tra LocalDate/LocalDateTime. Một chuỗi có thể khác định dạng hoặc thiếu thành phần; hãy parse đúng kiểu, xác thực và so bằng API.

## 5. Instant: bình đẳng và thứ tự trên trục thời gian

**Instant** mô tả một thời điểm tuyệt đối trên dòng thời gian UTC ở độ chính xác nano giây theo mô hình của java.time.

~~~java
Instant first = Instant.parse("2025-01-01T01:00:00Z");
Instant second = Instant.ofEpochSecond(1735693200L);

boolean sameInstant = first.equals(second); // true
boolean sameOrdering = first.compareTo(second) == 0; // true
~~~

Ở đây **1735693200 giây** tính từ Unix epoch tương ứng **2025-01-01T01:00:00Z**. Cả hai biểu diễn cùng một mốc nên equals đúng.

Dùng:

- **Instant.equals** khi yêu cầu cùng một vị trí thời gian.
- **Instant.isBefore** và **Instant.isAfter** cho quan hệ trước/sau.
- **Instant.compareTo** cho thứ tự sắp xếp Instant, ví dụ **Collections.sort** hoặc **TreeMap<Instant, ...>**.

**Instant không lưu tên time zone gốc.** Nếu dịch vụ A gửi cùng sự kiện theo giờ UTC+07 và dịch vụ B theo UTC, việc chuẩn hóa sang Instant giúp xác định cùng thời điểm mà không phải so chuỗi hiển thị.

### Chính xác đến nano giây

**Instant.equals** đòi hỏi cùng giây và nano giây. Hai thời điểm chỉ chênh một nano giây không bằng nhau. Đừng tự cắt về milli giây hoặc so string nếu nghiệp vụ không quy định độ chính xác ấy. Nếu log hoặc database chỉ lưu milli giây, hãy định nghĩa rõ bước làm tròn/truncation trước khi so sánh.

## 6. OffsetDateTime: cùng Instant chưa chắc equals

**OffsetDateTime** lưu cả local date-time lẫn **ZoneOffset**. Hai đối tượng có thể biểu diễn **cùng một Instant** nhưng **khác local fields và offset**.

Ví dụ:

~~~java
Instant moment = Instant.parse("2025-01-01T01:00:00Z");

OffsetDateTime a = moment.atOffset(ZoneOffset.ofHours(7));
// 2025-01-01T08:00+07:00

OffsetDateTime b = moment.atOffset(ZoneOffset.UTC);
// 2025-01-01T01:00Z

boolean equality = a.equals(b); // false
boolean sameMoment = a.isEqual(b); // true
boolean sameInstant = a.toInstant().equals(b.toInstant()); // true
~~~

**OffsetDateTime.equals** kiểm tra biểu diễn local date-time và offset. **isEqual** chỉ so vị trí Instant trên timeline. Đây là hai câu hỏi nghiệp vụ khác nhau:

- "Hai bản ghi có **cùng ngày/giờ địa phương và offset** không?" — dùng equals.
- "Hai bản ghi có xảy ra ở **cùng thời điểm tuyệt đối** không?" — dùng isEqual hoặc so Instant.

### compareTo với OffsetDateTime cần đặc biệt chú ý

**OffsetDateTime.compareTo** trước tiên so Instant; nếu hai giá trị cùng Instant, nó còn so các trường local để giữ tính **consistent with equals**.

~~~java
boolean zeroNaturalCompare = a.compareTo(b) == 0; // false

boolean zeroTimelineCompare =
        OffsetDateTime.timeLineOrder().compare(a, b) == 0; // true
~~~

**Không suy luận rằng a.isEqual(b) thì a.compareTo(b)==0.** Đặc biệt khi đưa OffsetDateTime vào sorted collections, lựa chọn Comparator ảnh hưởng tới việc hai giá trị có bị coi là một khóa hay không.

## 7. ZonedDateTime: offset, time zone và cùng mốc thời gian

**ZonedDateTime** chứa ngày–giờ địa phương, một **ZoneId** (ví dụ Asia/Ho_Chi_Minh) và offset được xác định theo quy tắc của zone tại mốc đó.

~~~java
Instant moment = Instant.parse("2025-01-01T01:00:00Z");

ZonedDateTime hoChiMinh = moment.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime utc = moment.atZone(ZoneOffset.UTC);

boolean sameValue = hoChiMinh.equals(utc); // false
boolean sameMoment = hoChiMinh.isEqual(utc); // true
boolean sameInstant = hoChiMinh.toInstant().equals(utc.toInstant()); // true
~~~

Ở ví dụ này, **cùng Instant** được hiển thị lần lượt theo UTC+07 và UTC. **equals** của ZonedDateTime bao gồm biểu diễn ngày/giờ và thông tin zone tương ứng; không chỉ so Instant. Cần lưu vùng thời gian ban đầu nếu ứng dụng quan tâm các quy tắc giờ địa phương của địa điểm.

**ZonedDateTime.withZoneSameInstant(otherZone)** đổi cách hiển thị theo zone khác **nhưng giữ Instant**. Nếu muốn so sự kiện theo trục thời gian, chuyển sang Instant là rõ nhất.

**ZonedDateTime.compareTo** cũng có thể dùng thông tin ngoài Instant khi hai giá trị cùng thời điểm, để giữ sự phù hợp với equals. Vì vậy **so compareTo bằng 0** và **so isEqual** không đồng nghĩa khi ZoneId khác nhau.

### Cùng giờ local có thể không cùng Instant

Hai giá trị "2025-01-01 08:00" ở UTC và UTC+07 là những Instant khác nhau. Phải thêm zone/offset chính xác trước khi hỏi "sự kiện nào xảy ra trước?".

### DST: local time có thể mơ hồ

Với vùng có daylight saving time, một giờ local có thể không tồn tại (**gap**) hoặc xảy ra hai lần (**overlap**). Không lấy **LocalDateTime.equals** để suy "chắc chắn cùng một sự kiện" nếu thiếu zone/offset giải quyết sự mơ hồ. Khi quy đổi LocalDateTime sang ZonedDateTime, áp dụng quy tắc ZoneRules, offset và chính sách nghiệp vụ phù hợp.

## 8. Bảng chọn equals, isEqual, compareTo và Instant

| Kiểu | equals thường xét | So thứ tự | Cách so "cùng thời điểm tuyệt đối" |
| --- | --- | --- | --- |
| LocalDate | Ngày ISO | compareTo/isBefore/isAfter; isEqual dùng epoch day với ChronoLocalDate | Không thể xác định khi chưa có giờ và zone |
| LocalTime | Giờ–phút–giây–nano trong ngày | compareTo/isBefore/isAfter | Không thể xác định khi chưa có ngày và zone |
| LocalDateTime | Ngày và giờ local | compareTo/isBefore/isAfter theo local timeline | Chuyển thành Instant với zone/offset thích hợp trước |
| Instant | Vị trí trên timeline | compareTo/isBefore/isAfter | equals/isEqual theo Instant (Instant có equals) |
| OffsetDateTime | Local date-time và offset | compareTo có tie-break local; isBefore/isAfter theo Instant | isEqual hoặc toInstant().equals(...) |
| ZonedDateTime | Local date-time, offset và zone | compareTo có tie-break; isBefore/isAfter theo Instant | isEqual hoặc toInstant().equals(...) |
| Duration | Số giây và nano giây sau chuẩn hóa nội bộ | compareTo | Đây là **khoảng thời gian**, không phải một Instant |
| Period | Bộ năm–tháng–ngày ISO | Không dùng như Instant; xem trường và normalized() | Đây là **khoảng lịch**, không phải một Instant |

**Không có một phương thức isEqual giống hệt nhau cho mọi loại:** chẳng hạn **LocalDate.isEqual(ChronoLocalDate)** dựa vào epoch day, còn **ZonedDateTime.isEqual(...)** dựa vào Instant. **Instant** tự dùng equals/compareTo/isBefore/isAfter; không cần một phương thức isEqual tương tự ZonedDateTime.

Khi hai giá trị thuộc **hai kiểu khác nhau** như OffsetDateTime và ZonedDateTime, không gọi bừa **equals** để khẳng định cùng mốc; hãy chuyển cả hai về **Instant** khi đó chính là khái niệm cần so.

## 9. HashMap, HashSet và hợp đồng equals/hashCode

Nhiều cấu trúc dữ liệu Java dựa vào **equals** và **hashCode**, không dựa vào danh tính tham chiếu, để nhận diện khóa hoặc phần tử trùng.

~~~java
LocalDate first = LocalDate.of(2025, 2, 1);
LocalDate second = LocalDate.parse("2025-02-01");

Set<LocalDate> dates = new HashSet<>();
dates.add(first);
dates.add(second);

System.out.println(dates.size()); // 1

Map<LocalDate, String> holidays = new HashMap<>();
holidays.put(first, "Holiday");
System.out.println(holidays.get(second)); // Holiday
~~~

Vì **LocalDate.equals** xác nhận cùng ngày và **hashCode** tương thích, HashSet coi hai ngày là trùng và HashMap truy xuất được bằng key bằng giá trị dù tham chiếu khác.

### Không dùng IdentityHashMap để lập chỉ mục ngày giờ

**IdentityHashMap** kiểm tra sự trùng khóa theo **tham chiếu**, không theo equals. Nó không phù hợp khi nghiệp vụ nói rằng hai LocalDate có cùng ngày thì phải là cùng key. Việc kết quả trên một JDK có vẻ đúng vì caching không tạo hợp đồng ổn định.

**System.identityHashCode(object)** cũng không phải giá trị băm nghiệp vụ của ngày. Muốn key ổn định theo giá trị, dùng chính LocalDate/Instant/YearMonth... phù hợp và cấu trúc Map theo equals.

### Key của Map cần đúng ngữ nghĩa miền dữ liệu

- Lịch nghỉ theo ngày: **LocalDate**.
- Sự kiện theo thời điểm trên timeline: **Instant**.
- Quy tắc lịch địa phương gắn vùng thời gian: có thể cần **LocalDateTime + ZoneId**, hoặc ZonedDateTime tùy contract.
- Bảng ngày/giờ theo offset của protocol: **OffsetDateTime** nếu cần giữ offset ban đầu.

Nếu hai OffsetDateTime là cùng Instant nhưng khác offset, dùng chúng làm khóa của **HashMap<OffsetDateTime,...>** cho ra **hai key** theo equals. Nếu nghiệp vụ muốn một key theo thời điểm tuyệt đối, chuẩn hóa sang **Instant** trước khi đưa vào Map.

## 10. TreeSet/TreeMap: comparator có thể đổi ý nghĩa trùng khóa

**HashSet** sử dụng equals/hashCode. **TreeSet** sử dụng comparator hoặc natural ordering để xác định thứ tự, đồng thời coi hai phần tử là trùng nếu **compare(a,b) == 0**.

Xét hai OffsetDateTime biểu diễn cùng Instant nhưng khác offset:

~~~java
OffsetDateTime a = OffsetDateTime.parse(
        "2025-01-01T08:00+07:00");
OffsetDateTime b = OffsetDateTime.parse(
        "2025-01-01T01:00Z");

Set<OffsetDateTime> hash = new HashSet<>();
hash.add(a);
hash.add(b);
// hash.size() == 2 vì a.equals(b) là false.

Set<OffsetDateTime> byTimeline =
        new TreeSet<>(OffsetDateTime.timeLineOrder());
byTimeline.add(a);
byTimeline.add(b);
// byTimeline.size() == 1 vì comparator trả 0 trên cùng Instant.
~~~

**OffsetDateTime.timeLineOrder()** có chủ đích bỏ qua sự khác biệt local date-time và offset, chỉ so timeline. Vì vậy TreeSet ở đây hoạt động như một tập **các thời điểm tuyệt đối**, không phải tập các **OffsetDateTime phân biệt theo equals**.

Đây là việc lựa chọn **quy tắc tương đương** của sorted collection. Comparator timeline không nhất quán với equals trong trường hợp cùng Instant khác offset; hãy xác nhận điều này là chủ ý trước khi sử dụng TreeSet/TreeMap. Nếu cần lưu **hai offset gốc**, dùng natural ordering của OffsetDateTime hoặc chọn một cấu trúc dữ liệu khác.

**Khuyến nghị dễ kiểm soát:** nếu ý định duy nhất là khử trùng mốc thời gian, tạo **Set<Instant>** thay vì dùng comparator có thể gây ngạc nhiên trên OffsetDateTime. Nếu cần giữ bản ghi và offset gốc, nên quyết định rõ khóa đại diện và cách gom nhiều bản ghi vào một mốc.

## 11. Immutability: plusDays không làm thay đổi ngày cũ

~~~java
LocalDate oldDate = LocalDate.of(2025, 2, 1);
LocalDate nextDate = oldDate.plusDays(1);

System.out.println(oldDate);  // 2025-02-01
System.out.println(nextDate); // 2025-02-02
~~~

Các phép **plus**, **minus**, **with** trên các value types java.time trả giá trị tính toán, không tự sửa nội dung instance cũ.

**Không suy diễn mỗi phép toán trả về một tham chiếu mới.** Nếu kết quả bằng chính giá trị đầu vào (ví dụ cộng 0 ngày), implementation có thể trả lại cùng object. Điều này hợp lệ với value-based classes; dùng **equals** để xác định kết quả có cùng giá trị hay không.

Vì immutable, một **LocalDate** có thể được dùng làm khóa Map ổn định về giá trị. Khác với key có trường mutable ảnh hưởng hashCode, ngày trong LocalDate không âm thầm đổi hash khi người dùng làm thao tác thời gian trên nó.

**An toàn chia sẻ giữa các thread** không có nghĩa dùng LocalDate làm công cụ đồng bộ: immutable giúp nhiều thread đọc cùng giá trị an toàn, còn monitor lock phải được thiết kế riêng.

## 12. Duration và Period: hai loại "khoảng thời gian" khác nhau

**Duration** đo lượng thời gian theo giây/nano trên timeline. **Period** biểu diễn lượng thời gian theo **năm, tháng, ngày lịch**. Hai kiểu đều value-based, nhưng **equals** của chúng có ngữ nghĩa riêng.

### Duration: hai cách biểu diễn 90 phút có cùng giá trị

~~~java
Duration a = Duration.ofMinutes(90);
Duration b = Duration.parse("PT1H30M");

System.out.println(a.equals(b)); // true
~~~

Duration lưu tổng thời lượng đã chuẩn hóa theo thành phần giây/nano. Cách tạo khác nhau không tạo ra "hai thời lượng khác nhau" khi giá trị thực là một.

### Period: 12 tháng không equals một năm trước khi chuẩn hóa

~~~java
Period a = Period.ofYears(1);
Period b = Period.ofMonths(12);

System.out.println(a.equals(b)); // false
System.out.println(a.equals(b.normalized())); // true
~~~

**Period.equals** xét bộ **years, months, days** như được lưu, không tự quy đổi mọi tháng sang năm khi so. **normalized()** điều chỉnh thành phần years/months thành dạng chuẩn hóa thích hợp; nó không thể chuyển số ngày sang tháng một cách phổ quát vì độ dài tháng thay đổi.

**Không dùng phép so sánh Period/Duration để thay thế phép so sánh Instant.** Một khoảng thời gian và một mốc thời gian là hai khái niệm khác nhau.

## 13. Cùng "một ngày" không phải lúc nào là cùng "24 giờ" qua DST

Khi một time zone thay đổi giờ mùa hè, cộng **một ngày lịch** có thể giữ cùng giờ trên đồng hồ nhưng không tương đương cộng **24 giờ elapsed**.

Ví dụ độc lập với ngày cố định trong Europe/Paris:

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2025, 3, 29, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime nextCalendarDay =
        start.plus(Period.ofDays(1));
ZonedDateTime after24Hours =
        start.plus(Duration.ofDays(1));

System.out.println(nextCalendarDay);
// 2025-03-30T12:00+02:00[Europe/Paris]

System.out.println(after24Hours);
// 2025-03-30T13:00+02:00[Europe/Paris]

System.out.println(nextCalendarDay.isEqual(after24Hours));
// false
~~~

Ngày 30/03/2025 ở Paris có bước chuyển giờ mùa hè. **Period.ofDays(1)** là bước lịch, còn **Duration.ofDays(1)** luôn đại diện 24 giờ theo giây; kết quả có thể khác Instant. Đây là ví dụ vì sao phải xác định nghiệp vụ "một ngày tiếp theo" hay "đúng 24 giờ sau" trước khi quyết định có bằng nhau không.

Quy tắc múi giờ có thể được cập nhật trong cơ sở dữ liệu timezone của JDK. Với bài toán tương lai, phải dựa vào ZoneId và quy tắc được cập nhật phù hợp; không hardcode mọi ngày luôn dài 24 giờ trên đồng hồ địa phương.

## 14. isEqual theo hai hệ lịch: đừng nhầm với equals

Java cung cấp các kiểu **ChronoLocalDate** cho hệ lịch khác ngoài ISO khi ứng dụng thực sự cần tương tác với lịch địa phương. **LocalDate** là lịch ISO, **JapaneseDate** là một lịch khác.

~~~java
LocalDate iso = LocalDate.of(2025, 3, 1);
JapaneseDate japanese = JapaneseDate.from(iso);

boolean sameEpochDay = iso.isEqual(japanese); // true
boolean sameObjectValue = iso.equals(japanese); // false

boolean sameTimelineDay =
        ChronoLocalDate.timeLineOrder()
                .compare(iso, japanese) == 0; // true
~~~

Đoạn này cần import **java.time.LocalDate**, **java.time.chrono.JapaneseDate** và **java.time.chrono.ChronoLocalDate**.

**isEqual** ở đây so **cùng epoch day**, bất kể chronology. **equals** của LocalDate đòi cùng kiểu/ngữ nghĩa lịch ISO, nên khác JapaneseDate. Comparator **ChronoLocalDate.timeLineOrder** có chủ đích bỏ qua chronology để so ngày theo timeline.

Chỉ dùng API chronology khi cần biểu diễn lịch của người dùng. Với dữ liệu chuẩn trao đổi giữa các hệ thống, tài liệu java.time khuyến nghị ưu tiên các kiểu ISO trong **java.time** để tránh nhập nhằng. Ví dụ này giúp hiểu sự khác biệt giữa **so bằng giá trị theo lịch** và **so cùng ngày trên timeline**, không khuyến khích trộn lịch tùy tiện.

## 15. Vì sao không dùng value-based object cho synchronized hoặc identity hash?

Tài liệu **Value-based Classes** của JDK cảnh báo các cơ chế phụ thuộc danh tính object có thể cho hành vi không dự đoán được, hoặc thay đổi ở phiên bản tương lai:

- **synchronized(date)**, **date.wait()**, **date.notify()** và mọi cơ chế giành monitor qua chính value-based instance;
- **a == b** khi muốn kiểm tra giá trị, thay vì kiểm tra tham chiếu;
- **System.identityHashCode(date)** để tạo định danh hoặc băm nghiệp vụ;
- **IdentityHashMap<LocalDate, ...>** để khử trùng theo ngày;
- Những logic cần gắn định danh lâu dài hoặc lock với một instance value-based có thể bị runtime thay thế/tái sử dụng.

**Không dùng value-based instance làm lock.** Hai giá trị ngày bằng nhau không nhất thiết cùng monitor; ngược lại, hai phần chương trình có thể bất ngờ nhận cùng instance. Cả hai trường hợp đều khiến logic synchronized theo "ngày" không có hợp đồng đúng.

Mẫu đúng nếu một component cần bảo vệ trạng thái riêng:

~~~java
final class SchedulerState {
    private final Object lock = new Object();
    private LocalDate currentDate = LocalDate.of(2025, 1, 1);

    public void update(LocalDate next) {
        synchronized (lock) {
            currentDate = next;
        }
    }

    public LocalDate read() {
        synchronized (lock) {
            return currentDate;
        }
    }
}
~~~

Đây là class minh họa có thể biên dịch khi import **java.time.LocalDate**. **lock** thuộc quyền sở hữu của component, được tạo rõ và không bị lẫn với một giá trị ngày giờ. **currentDate** là reference tới một immutable LocalDate; việc thay đổi reference được bảo vệ bởi monitor riêng.

Nếu nhiều task cần **phối hợp theo key ngày**, hãy dùng bộ điều phối/concurrency primitive được thiết kế theo ownership/định danh ổn định, không trực tiếp dùng object LocalDate làm monitor. Không khuyến khích dùng synchronized trên giá trị dù ở một JDK hiện tại thấy chương trình chạy.

## 16. Ngoại lệ cần nhớ: Month và DayOfWeek là enum

**Month** và **DayOfWeek** của java.time là **enum types**. Theo quy tắc ngôn ngữ Java, mỗi enum constant có danh tính ổn định duy nhất trong kiểu enum đó; **==** là phép so sánh đúng và thường được dùng cho enum:

~~~java
boolean sameMonth = Month.JANUARY == Month.of(1); // true

DayOfWeek day = DayOfWeek.MONDAY;
boolean monday = day == DayOfWeek.MONDAY; // true
~~~

**Không mở rộng ngoại lệ này sang LocalDate, LocalTime, Instant, ZoneId hoặc OffsetDateTime.** Chúng không phải enum chỉ vì nằm cùng package.

### Null và Objects.equals

~~~java
LocalDate left = null;
LocalDate right = null;

boolean bothAbsent = Objects.equals(left, right); // true
boolean sameAsDate = Objects.equals(left, LocalDate.now()); // false
~~~

Đây là **đoạn minh họa** cần import **java.util.Objects**, và dòng LocalDate.now() phụ thuộc thời gian chạy nên chỉ minh họa giá trị boolean đối với null. **Objects.equals(null,null)** là true, khác với câu hỏi "hai ngày hợp lệ có bằng nhau?" khi dữ liệu null là lỗi. Nếu domain không cho phép null, kiểm tra dữ liệu và báo lỗi sớm thay vì coi hai giá trị thiếu là cùng một ngày.

**compareTo(null)** thường ném NullPointerException vì đối số không hợp lệ; **equals(null)** của các kiểu giá trị trả false. Đừng dùng == như một cách "chống null" trong nghiệp vụ so sánh.

## 17. Chương trình Java 17 chạy độc lập, có đầu ra xác định

Tạo tệp **DateTimeValueSemanticsDemo.java**:

~~~java
import java.time.*;
import java.util.*;

public class DateTimeValueSemanticsDemo {
    public static void main(String[] args) {
        LocalDate dateA = LocalDate.of(2025, 2, 1);
        LocalDate dateB = LocalDate.parse("2025-02-01");

        System.out.println("date equals: " + dateA.equals(dateB));
        System.out.println("date compareTo zero: "
                + (dateA.compareTo(dateB) == 0));

        Set<LocalDate> uniqueDates =
                new HashSet<>(Arrays.asList(dateA, dateB));
        System.out.println("unique dates: " + uniqueDates.size());

        Map<LocalDate, String> holidays = new HashMap<>();
        holidays.put(dateA, "Holiday");
        System.out.println("map lookup: " + holidays.get(dateB));

        LocalDate next = dateA.plusDays(1);
        System.out.println("original/next: " + dateA + " / " + next);
        System.out.println("isBefore: " + dateA.isBefore(next));

        Instant instant = Instant.parse("2025-01-01T01:00:00Z");
        OffsetDateTime offsetA =
                instant.atOffset(ZoneOffset.ofHours(7));
        OffsetDateTime offsetB =
                instant.atOffset(ZoneOffset.UTC);

        System.out.println("offset equals: " + offsetA.equals(offsetB));
        System.out.println("offset isEqual: " + offsetA.isEqual(offsetB));
        System.out.println("offset compareTo zero: "
                + (offsetA.compareTo(offsetB) == 0));
        System.out.println("timeline comparator zero: "
                + (OffsetDateTime.timeLineOrder()
                        .compare(offsetA, offsetB) == 0));

        Set<OffsetDateTime> defaultKeys =
                new HashSet<>(Arrays.asList(offsetA, offsetB));
        Set<OffsetDateTime> instantKeys =
                new TreeSet<>(OffsetDateTime.timeLineOrder());
        instantKeys.add(offsetA);
        instantKeys.add(offsetB);
        System.out.println("hash set size: " + defaultKeys.size());
        System.out.println("timeline set size: " + instantKeys.size());

        ZonedDateTime zonedA =
                instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        ZonedDateTime zonedB = instant.atZone(ZoneOffset.UTC);

        System.out.println("zoned equals: " + zonedA.equals(zonedB));
        System.out.println("zoned isEqual: " + zonedA.isEqual(zonedB));
        System.out.println("zoned instant equals: "
                + zonedA.toInstant().equals(zonedB.toInstant()));

        LocalDateTime wallA =
                LocalDateTime.of(2025, 1, 1, 12, 0);
        LocalDateTime wallB =
                LocalDateTime.parse("2025-01-01T12:00");

        System.out.println("local fields equal: " + wallA.equals(wallB));

        Duration durationA = Duration.ofMinutes(90);
        Duration durationB = Duration.parse("PT1H30M");
        System.out.println("duration equals: "
                + durationA.equals(durationB));

        Period periodA = Period.ofYears(1);
        Period periodB = Period.ofMonths(12);
        System.out.println("period equals: " + periodA.equals(periodB));
        System.out.println("normalized period equals: "
                + periodA.equals(periodB.normalized()));

        Clock fixed = Clock.fixed(instant, ZoneOffset.UTC);
        System.out.println("fixed clock date: " + LocalDate.now(fixed));

        Object lock = new Object();
        synchronized (lock) {
            System.out.println("lock: separate Object");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac DateTimeValueSemanticsDemo.java
java DateTimeValueSemanticsDemo
~~~

**Stdout đã chạy và kiểm chứng:**

~~~text
date equals: true
date compareTo zero: true
unique dates: 1
map lookup: Holiday
original/next: 2025-02-01 / 2025-02-02
isBefore: true
offset equals: false
offset isEqual: true
offset compareTo zero: false
timeline comparator zero: true
hash set size: 2
timeline set size: 1
zoned equals: false
zoned isEqual: true
zoned instant equals: true
local fields equal: true
duration equals: true
period equals: false
normalized period equals: true
fixed clock date: 2025-01-01
lock: separate Object
~~~

Tất cả kết quả dùng dữ liệu cố định, không đọc thời gian thực của máy. **Clock.fixed(...)** cho phép kiểm thử các phép toán dùng ngày hiện tại theo một mốc xác định mà không phụ thuộc ngày chạy test. Điều này hữu ích trong các hệ thống có quy tắc ngày, thời hạn hoặc múi giờ.

**Không có dòng in kết quả của == giữa hai LocalDate**, vì giá trị boolean của phép so sánh tham chiếu không phải hợp đồng nghiệp vụ và không phải dữ liệu đầu ra đáng khuyến khích cho value-based class.

## 18. Chương trình bổ sung: lịch khác và chuyển giờ mùa hè

Ví dụ độc lập này minh họa hai ý: cùng epoch day dưới hai chronology có thể **isEqual** nhưng không **equals**; và cộng một ngày lịch khác cộng 24 giờ qua DST.

Tạo tệp **ChronoDstDemo.java**:

~~~java
import java.time.*;
import java.time.chrono.*;

public class ChronoDstDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2025, 3, 1);
        JapaneseDate jp = JapaneseDate.from(iso);

        System.out.println(
                "chrono equal timeline: " + iso.isEqual(jp));
        System.out.println(
                "chrono equals object: " + iso.equals(jp));
        System.out.println(
                "chrono timeline order zero: "
                + (ChronoLocalDate.timeLineOrder()
                        .compare(iso, jp) == 0));

        System.out.println(
                "enum month: " + (Month.JANUARY == Month.of(1)));

        ZonedDateTime start = ZonedDateTime.of(
                2025, 3, 29, 12, 0, 0, 0,
                ZoneId.of("Europe/Paris"));

        ZonedDateTime calendarDay =
                start.plus(Period.ofDays(1));
        ZonedDateTime elapsed24h =
                start.plus(Duration.ofDays(1));

        System.out.println("calendar day: " + calendarDay);
        System.out.println("elapsed 24h: " + elapsed24h);
        System.out.println("same instant: "
                + calendarDay.isEqual(elapsed24h));
    }
}
~~~

Chạy:

~~~bash
javac ChronoDstDemo.java
java ChronoDstDemo
~~~

Đầu ra đã kiểm chứng:

~~~text
chrono equal timeline: true
chrono equals object: false
chrono timeline order zero: true
enum month: true
calendar day: 2025-03-30T12:00+02:00[Europe/Paris]
elapsed 24h: 2025-03-30T13:00+02:00[Europe/Paris]
same instant: false
~~~

**Lưu ý:** ví dụ DST sử dụng dữ liệu timezone của JDK tại thời điểm chạy. Quy tắc timezone là dữ liệu có thể được cập nhật theo quyết định của các quốc gia. Với thời gian tương lai hoặc môi trường có tzdb khác, kiểm thử với bộ quy tắc cụ thể của hệ thống đang triển khai.

## 19. Tình huống ứng dụng và cách chọn khóa/so sánh

### Tình huống A — Lưu lịch nghỉ, ngày sinh, ngày đóng sổ

Yêu cầu là ngày trong lịch, **không** phải thời điểm UTC. Dùng **LocalDate** làm khóa và **equals/isBefore/isAfter** thích hợp. Không lấy midnight UTC để đại diện một ngày local nếu điều đó có thể làm ngày bị dịch qua zone.

### Tình huống B — Dữ liệu sự kiện từ nhiều quốc gia

Các bản ghi có thể mang offset/timezone khác nhau nhưng nói về cùng mốc. Chuẩn hóa chúng sang **Instant** để sắp theo thời điểm thực hoặc khử trùng. Nếu muốn giữ offset/time zone gốc để hiển thị, lưu riêng thuộc tính biểu diễn cùng dữ liệu sự kiện.

### Tình huống C — Lịch họp tại một địa điểm

Lưu **ZoneId** thực tế của nơi diễn ra sự kiện và giờ local theo yêu cầu; quy tắc DST có thể ảnh hưởng tới việc chuyển sang Instant. Khi so sánh mốc xảy ra, lấy **Instant** tương ứng. Hai giờ local bằng nhau không đủ để chứng minh hai lịch hẹn xảy ra cùng lúc.

### Tình huống D — Bộ lọc lịch sử theo khoảng

Nếu backend lọc timestamp, hãy chuyển biên lọc sang Instant theo zone nghiệp vụ. So sánh **Instant.isBefore/isAfter** hoặc **compareTo** sau khi xác định biên inclusive/exclusive. Không so chuỗi giờ hiển thị giữa nhiều zone như một proxy cho thứ tự thời gian.

### Tình huống E — Cấu trúc dữ liệu và concurrency

Nếu cần Map của sự kiện theo thời điểm, chọn **Map<Instant,...>**. Nếu cần những bản ghi cùng Instant nhưng khác offset được giữ riêng, chọn khóa tổng hợp hoặc OffsetDateTime theo contract. Khi cần lock, dùng **Object lock** thuộc quyền sở hữu component hoặc một concurrency primitive; không khóa trên chính đối tượng ngày giờ.

## 20. Các lỗi phổ biến và bài tập

### Lỗi 1 — So hai ngày bằng ==

~~~java
LocalDate a = LocalDate.parse("2025-02-01");
LocalDate b = LocalDate.of(2025, 2, 1);

// Sai về ý nghĩa nghiệp vụ:
// boolean sameDay = a == b;

boolean sameDay = a.equals(b); // Đúng.
~~~

**Giải thích:** == kiểm tra identity, trong khi LocalDate là value-based class.

### Lỗi 2 — Cho rằng cùng Instant đồng nghĩa equals với OffsetDateTime

~~~java
OffsetDateTime a = OffsetDateTime.parse(
        "2025-01-01T08:00+07:00");
OffsetDateTime b = OffsetDateTime.parse(
        "2025-01-01T01:00Z");

// a.equals(b) == false
// a.isEqual(b) == true
~~~

**Giải thích:** equals giữ ý nghĩa biểu diễn local + offset; isEqual so timeline.

### Lỗi 3 — Dùng LocalDateTime để phân biệt cùng thời điểm toàn cầu

**Không đủ thông tin:** LocalDateTime không mang ZoneId hoặc ZoneOffset. Muốn so trục thời gian, xác định zone/offset trước và chuyển sang Instant.

### Lỗi 4 — Dùng IdentityHashMap để gom ngày

**Đáp án:** không nên. Map này nhận diện khóa theo tham chiếu. Dùng HashMap<LocalDate,...> khi yêu cầu cùng giá trị ngày là một khóa; dùng Map<Instant,...> nếu khóa là mốc thời gian tuyệt đối.

### Lỗi 5 — Đồng bộ trên một LocalDate

**Đáp án:** không dùng **synchronized(date)** vì value-based object không bảo đảm identity làm monitor theo cách ứng dụng cần. Tạo dedicated lock hoặc chọn cơ chế concurrency khác.

### Lỗi 6 — Cho rằng Period.ofMonths(12) luôn equals Period.ofYears(1)

**Đáp án:** không. Period lưu năm/tháng/ngày theo thành phần; hãy sử dụng **normalized()** nếu mục tiêu là so dạng đã chuẩn hóa years/months và điều đó phù hợp miền dữ liệu.

### Lỗi 7 — Cho rằng TreeSet luôn dùng equals giống HashSet

**Đáp án:** TreeSet dùng comparator/natural order để quyết định phần tử trùng theo compare==0. Với **OffsetDateTime.timeLineOrder**, hai biểu diễn cùng Instant bị coi là tương đương và chỉ giữ một phần tử. HashSet<OffsetDateTime> dùng equals và có thể giữ cả hai.

### Lỗi 8 — Dùng == cho mọi kiểu của java.time đều sai?

**Đáp án:** cần phân biệt. Với **Month** và **DayOfWeek** là enum, **==** hợp lệ và đúng theo hợp đồng enum. Với **LocalDate**, **Instant**, **OffsetDateTime**, **ZonedDateTime**, không dùng == để kiểm tra giá trị.

### Bài tự kiểm tra

1. Hai LocalDate từ parse/of cùng ngày được coi bằng nhau bằng phương thức nào?
2. Hai ZonedDateTime cùng Instant khác ZoneId: equals hay isEqual biểu diễn điều kiện cùng mốc?
3. HashSet<OffsetDateTime> và TreeSet<>(OffsetDateTime.timeLineOrder()) khác nhau thế nào?
4. Khi nào dùng LocalDate thay vì Instant làm khóa bản ghi?
5. Vì sao synchronized trên LocalDate không phải khóa thích hợp?
6. Khi thêm một ngày qua DST, Period và Duration có thể khác nhau thế nào?

**Đáp án ngắn:** (1) equals; (2) isEqual hoặc so toInstant; (3) equals vs comparator timeline; (4) ngày lịch vs sự kiện thời điểm; (5) value-based identity không đáng dựa; (6) ngày lịch giữ cùng giờ local, Duration 24 giờ giữ đúng elapsed seconds.

## 21. Tổng kết và tài liệu chính thức

**Những quy tắc cần nhớ:**

1. **java.time value-based objects được so theo giá trị**, không theo identity. Không dựa vào ==, cache, identity hash hoặc monitor của đối tượng để viết nghiệp vụ.
2. **LocalDate/LocalTime/LocalDateTime** mô tả giá trị local; **Instant** là mốc timeline; **OffsetDateTime/ZonedDateTime** chứa thêm cách biểu diễn theo offset/zone.
3. **equals của OffsetDateTime/ZonedDateTime không đồng nghĩa isEqual**. Hai bản ghi có thể cùng Instant nhưng khác offset/zone.
4. **compareTo của OffsetDateTime** có tie-break để phù hợp equals; **timeLineOrder** chỉ quan tâm Instant. Chọn comparator sẽ thay đổi ngữ nghĩa trùng key trong TreeSet/TreeMap.
5. **HashMap/HashSet dùng equals và hashCode**. Nếu cần khóa theo mốc tuyệt đối, chuẩn hóa sang Instant.
6. **Period là năm/tháng/ngày lịch**, còn **Duration** là thời lượng theo giây; so sánh và phép cộng qua DST có thể khác.
7. **Month/DayOfWeek là enum** nên == dùng được theo hợp đồng enum, khác các lớp giá trị ngày giờ.
8. **Clock.fixed(...)** hỗ trợ kiểm thử giá trị ngày giờ có đầu ra xác định; tránh lệ thuộc giờ hệ thống khi đang kiểm tra logic.
9. Tất cả các API trọng tâm của bài đều là Java 8+ và còn được tài liệu Java SE hiện đại duy trì.

**Tài liệu Java chính thức còn áp dụng:**

- **Value-based Classes** — mô tả giới hạn của identity, synchronization, identity hash và cách dùng equals: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/doc-files/ValueBased.html
- **Package java.time** — mô hình LocalDate, LocalTime, Instant, ZonedDateTime, Duration và Period: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/package-summary.html
- **LocalDate** — equals, isEqual với ChronoLocalDate, compareTo và plusDays: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- **Instant** — equals và thứ tự thời gian: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html
- **OffsetDateTime** — khác biệt giữa equals, isEqual, compareTo và timeLineOrder: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html
- **ZonedDateTime** — lưu ZoneId, xử lý DST, equals/isEqual và chuyển cùng Instant: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html
- **Duration** và **Period** — hai khái niệm khoảng thời gian và so sánh giá trị: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Period.html
- **ChronoLocalDate** — so cùng epoch day giữa nhiều chronology khi thật sự có nhu cầu: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/chrono/ChronoLocalDate.html
