# Tính tuổi và xử lý sinh nhật ngày 29 tháng 2 trong Java

Tính tuổi có vẻ chỉ là lấy năm hiện tại trừ năm sinh, nhưng phép trừ đó có thể sai trước ngày sinh nhật trong năm. Trường hợp sinh ngày **29 tháng 2** càng cần định nghĩa rõ: vào năm không nhuận, ngày 29/02 không tồn tại, vậy sinh nhật được tính vào ngày 28/02 hay 01/03?

Trong Java, nên dùng `LocalDate` để biểu diễn ngày sinh và ngày cần tính tuổi, sau đó áp dụng quy tắc nghiệp vụ rõ ràng. Đừng tính tuổi bằng cách chia số mili giây đã trôi cho số giây trung bình một năm, bởi năm nhuận và ngày sinh nhật trên lịch không được biểu diễn chính xác theo cách đó.

## 1. Vì sao phép trừ năm chưa đủ?

Giả sử một người sinh ngày `2000-06-20`. Khi tính tuổi tại `2025-01-10`, phép trừ `2025 - 2000 = 25` nhưng người đó **chưa đến sinh nhật lần thứ 25**. Tuổi hoàn chỉnh tại ngày đó là 24.

Cách tính phổ biến cho ngày sinh không phải 29/02:

1. Tính hiệu hai năm: `age = asOf.getYear() - birthDate.getYear()`.
2. Xác định sinh nhật trong năm cần tính.
3. Nếu ngày đang xét còn trước sinh nhật trong năm đó, trừ tuổi đi một.

Công thức tổng quát:

```text
tuổi = năm cần tính - năm sinh

nếu ngày cần tính < sinh nhật năm đó:
    tuổi = tuổi - 1
```

Cách so sánh **ngày/tháng/năm đầy đủ** xử lý đúng trường hợp ngày sinh trong năm nay còn ở phía trước. Tuy nhiên, để tính đúng cho người sinh ngày 29/02, cần xác định sinh nhật thay thế vào năm không nhuận trước khi áp dụng bước 3.

`LocalDate` phù hợp vì chứa ngày lịch không kèm giờ hoặc múi giờ. Tuổi thông thường là số năm lịch đã hoàn tất, không phải số chu kỳ 365 ngày đã trôi.

## 2. Năm nhuận và ngày 29 tháng 2

Theo lịch ISO dùng bởi `java.time`, một năm là năm nhuận nếu:

- Chia hết cho 4;
- ngoại trừ năm chia hết cho 100 thì không phải năm nhuận;
- nhưng năm chia hết cho 400 lại là năm nhuận.

Do đó:

| Năm | Năm nhuận? | Có ngày 29/02? |
| --- | --- | --- |
| 2024 | Có | Có |
| 2025 | Không | Không |
| 1900 | Không | Không |
| 2000 | Có | Có |
| 2100 | Không | Không |
| 2400 | Có | Có |

Trong Java, dùng `Year.isLeap(year)` thay vì tự viết logic năm nhuận nếu không có yêu cầu đặc biệt. Ví dụ:

```java
System.out.println(Year.isLeap(2024)); // true
System.out.println(Year.isLeap(2025)); // false
System.out.println(Year.isLeap(2000)); // true
System.out.println(Year.isLeap(2100)); // false
```

Đoạn mã cần `import java.time.Year;` và có thể đặt trong phương thức `main`. `LocalDate.of(2025, 2, 29)` sẽ ném `DateTimeException` vì ngày đó không tồn tại; Java không tự đổi ngày sinh thành 28/02 hay 01/03. Chính sách này phải do ứng dụng xác định.

## 3. Chọn quy tắc sinh nhật trong năm không nhuận

Với người sinh ngày `29/02`, thường gặp hai quy tắc nghiệp vụ:

**Chính sách A — tính vào ngày 28/02.** Trong năm không nhuận, sinh nhật thay thế là ngày cuối cùng của tháng 2. Nếu ngày tính tuổi là `28/02/2025`, người sinh `29/02/2000` đã tăng tuổi theo chính sách này.

**Chính sách B — tính vào ngày 01/03.** Trong năm không nhuận, sinh nhật thay thế là ngày đầu tiên của tháng 3. Vào `28/02/2025` người đó vẫn giữ tuổi cũ; đến `01/03/2025` mới tăng tuổi.

Không nên âm thầm chọn một chính sách rồi áp dụng cho mọi hệ thống. Ứng dụng pháp lý, hồ sơ dân sự, hợp đồng, bảo hiểm, trường học và nghiệp vụ quốc tế có thể phải tuân thủ quy tắc theo khu vực hoặc quy định riêng. Bài này trình bày hai chính sách lập trình phổ biến; ứng dụng phải xác nhận quy tắc phù hợp với miền nghiệp vụ của mình.

Ví dụ người sinh `2000-02-29`:

| Ngày đang xét | Chính sách sinh nhật 28/02 | Chính sách sinh nhật 01/03 |
| --- | ---: | ---: |
| 2024-02-28 (năm nhuận) | 23 | 23 |
| 2024-02-29 (năm nhuận) | 24 | 24 |
| 2025-02-28 (năm không nhuận) | 25 | 24 |
| 2025-03-01 (năm không nhuận) | 25 | 25 |
| 2028-02-28 (năm nhuận) | 27 | 27 |
| 2028-02-29 (năm nhuận) | 28 | 28 |

Bảng giả định người sinh còn sống và chỉ tính tuổi theo ngày lịch đã nêu; cột kết quả là số tuổi hoàn chỉnh. Đối với năm 2028, ngày sinh nhật thật 29/02 tồn tại nên hai chính sách cho kết quả giống nhau.

## 4. Xây dựng hàm tìm ngày sinh nhật trong một năm

Để tránh rải logic 29/02 ở nhiều nơi, tạo một phương thức duy nhất nhận ngày sinh, năm mục tiêu và chính sách. Nếu ngày sinh không phải 29/02, có thể thay năm của ngày sinh để tạo ngày/tháng tương ứng trong năm mục tiêu. Riêng 29/02 vào năm không nhuận, trả về ngày quy ước đã chọn.

Một enum giúp những lựa chọn nghiệp vụ dễ đọc hơn là một giá trị boolean:

```java
enum LeapDayPolicy {
    FEBRUARY_28,
    MARCH_1
}
```

Đoạn enum có thể nằm trong cùng tệp Java với class chứa hàm tính tuổi (chỉ để một class là `public` nếu lưu vào một tệp đơn giản).

Hàm tìm ngày kỷ niệm sinh nhật:

```java
static LocalDate anniversaryInYear(
        LocalDate birthDate,
        int year,
        LeapDayPolicy policy) {

    boolean leapDayBirth = birthDate.getMonthValue() == 2
            && birthDate.getDayOfMonth() == 29;

    if (leapDayBirth && !Year.isLeap(year)) {
        return policy == LeapDayPolicy.FEBRUARY_28
                ? LocalDate.of(year, 2, 28)
                : LocalDate.of(year, 3, 1);
    }

    return birthDate.withYear(year);
}
```

Phương thức cần `import java.time.*;`. Với ngày sinh `29/02` trong một năm nhuận, `withYear(year)` giữ được ngày 29/02. Với ngày sinh khác, chẳng hạn `31/05`, thay năm không làm thay đổi tháng/ngày vì ngày đó hợp lệ trong mọi năm. Nhánh đặc biệt chỉ cần áp dụng cho ngày 29/02 trong năm không nhuận.

Hàm yêu cầu `year` trong miền năm mà `LocalDate` hỗ trợ. Trong ứng dụng có input không đáng tin cậy, hãy kiểm tra năm mục tiêu và xử lý `DateTimeException` nếu dữ liệu nằm ngoài miền hợp lệ. Enum `policy` cũng nên được đảm bảo không null.

## 5. Tính tuổi tại một ngày bất kỳ bằng `LocalDate`

Sau khi biết ngày sinh nhật hợp lệ theo chính sách trong năm mục tiêu, tính tuổi hoàn chỉnh:

```java
static int ageOn(
        LocalDate birthDate,
        LocalDate asOf,
        LeapDayPolicy policy) {

    if (asOf.isBefore(birthDate)) {
        throw new IllegalArgumentException(
                "Ngày tính tuổi phải bằng hoặc sau ngày sinh"
        );
    }

    int age = asOf.getYear() - birthDate.getYear();
    LocalDate anniversary =
            anniversaryInYear(birthDate, asOf.getYear(), policy);

    if (asOf.isBefore(anniversary)) {
        age--;
    }
    return age;
}
```

Đây là phương thức dùng chung enum và hàm `anniversaryInYear` ở phần trước; không phải một chương trình đầy đủ độc lập. Nó hoạt động như sau:

1. Từ chối ngày tính tuổi trước ngày sinh. Nếu không kiểm tra, phép trừ năm có thể trả kết quả âm hoặc không hợp lệ về nghiệp vụ.
2. Tạm tính hiệu số năm lịch.
3. Tìm ngày kỷ niệm sinh nhật trong năm đang xét, đã áp dụng chính sách cho 29/02.
4. Nếu ngày đang xét còn trước ngày kỷ niệm, giảm một tuổi; nếu đến hoặc qua ngày đó, giữ nguyên kết quả.

**Lưu ý toán tử biên:** dùng `asOf.isBefore(anniversary)`, không dùng `!asOf.isAfter(anniversary)`, bởi ngày sinh nhật chính nó đã là ngày tăng tuổi. Tức là, trong chính sách 01/03, ngày `2025-03-01` cho tuổi mới, không đợi tới 02/03.

## 6. Ví dụ chạy được trên Java 17+

Ví dụ đầy đủ dưới đây cho phép đổi chính sách và thử nhiều ngày, giúp kiểm tra những trường hợp dễ sai quanh ngày 28/02, 29/02 và 01/03.

Lưu vào **`LeapDayAgeDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Year;

public class LeapDayAgeDemo {
    enum LeapDayPolicy {
        FEBRUARY_28,
        MARCH_1
    }

    static LocalDate anniversaryInYear(
            LocalDate birthDate, int year, LeapDayPolicy policy) {

        boolean leapDayBirth = birthDate.getMonthValue() == 2
                && birthDate.getDayOfMonth() == 29;

        if (leapDayBirth && !Year.isLeap(year)) {
            return policy == LeapDayPolicy.FEBRUARY_28
                    ? LocalDate.of(year, 2, 28)
                    : LocalDate.of(year, 3, 1);
        }

        return birthDate.withYear(year);
    }

    static int ageOn(
            LocalDate birthDate,
            LocalDate asOf,
            LeapDayPolicy policy) {

        if (asOf.isBefore(birthDate)) {
            throw new IllegalArgumentException(
                    "asOf must be on or after birthDate"
            );
        }

        int age = asOf.getYear() - birthDate.getYear();
        LocalDate anniversary =
                anniversaryInYear(birthDate, asOf.getYear(), policy);

        if (asOf.isBefore(anniversary)) {
            age--;
        }
        return age;
    }

    public static void main(String[] args) {
        LocalDate birth = LocalDate.of(2000, 2, 29);

        System.out.println("Feb28 policy on Feb28 : "
                + ageOn(birth, LocalDate.of(2025, 2, 28),
                        LeapDayPolicy.FEBRUARY_28));
        System.out.println("Mar1 policy on Feb28  : "
                + ageOn(birth, LocalDate.of(2025, 2, 28),
                        LeapDayPolicy.MARCH_1));
        System.out.println("Mar1 policy on Mar1   : "
                + ageOn(birth, LocalDate.of(2025, 3, 1),
                        LeapDayPolicy.MARCH_1));
        System.out.println("Feb28 policy on leap day: "
                + ageOn(birth, LocalDate.of(2024, 2, 29),
                        LeapDayPolicy.FEBRUARY_28));
        System.out.println("Next leap anniversary : "
                + anniversaryInYear(birth, 2028, LeapDayPolicy.MARCH_1));
        System.out.println("ChronoUnit years      : "
                + java.time.temporal.ChronoUnit.YEARS.between(
                        birth, LocalDate.of(2025, 2, 28)));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac LeapDayAgeDemo.java
java LeapDayAgeDemo
```

Đầu ra đã biên dịch/chạy thực tế:

```text
Feb28 policy on Feb28 : 25
Mar1 policy on Feb28  : 24
Mar1 policy on Mar1   : 25
Feb28 policy on leap day: 24
Next leap anniversary : 2028-02-29
ChronoUnit years      : 24
```

Phân tích:

- Vào `2025-02-28`, chính sách `FEBRUARY_28` tính tuổi 25; chính sách `MARCH_1` vẫn cho 24.
- Vào `2025-03-01`, chính sách `MARCH_1` cũng tính tuổi 25.
- Năm nhuận 2024 có ngày 29/02, nên đến ngày đó người sinh `2000-02-29` tròn 24 tuổi theo cả hai chính sách.
- `anniversaryInYear` trả `2028-02-29` cho năm nhuận; không cần quy đổi ngày sang 28/02 hay 01/03 khi ngày sinh thật tồn tại.
- `ChronoUnit.YEARS.between(birth, asOf)` trả 24 tại `2025-02-28` trong ví dụ. Đó là phép chênh lệch năm theo quy tắc `Temporal`, **không tự áp dụng chính sách sinh nhật riêng của ứng dụng**. Nếu cần quy tắc 29/02 nhất quán, dùng hàm nghiệp vụ tường minh.

## 7. Vì sao không chỉ gọi `Period.between()` hoặc `ChronoUnit.YEARS.between()`?

`Period.between(birthDate, asOf)` trả một `Period` gồm năm, tháng và ngày giữa hai `LocalDate`. `ChronoUnit.YEARS.between(birthDate, asOf)` trả số năm hoàn chỉnh theo quy tắc của các ngày đã cho. Cả hai đều hữu ích cho nhiều phép toán ngày giờ thông thường; tuy nhiên, **chúng không nhận vào chính sách nghiệp vụ “sinh nhật 29/02 ở năm không nhuận là 28/02 hay 01/03”**.

Ví dụ:

```java
LocalDate birth = LocalDate.of(2000, 2, 29);
LocalDate check = LocalDate.of(2025, 2, 28);

int years = (int) java.time.temporal.ChronoUnit.YEARS
        .between(birth, check);
// years = 24
```

Nếu nghiệp vụ chọn `FEBRUARY_28`, kết quả tuổi hoàn chỉnh ở ngày này là 25; vì thế không thể thay thế chính sách đó bằng phép `between` mà không điều chỉnh quy tắc. `Period` còn trả tháng/ngày, có thể hữu ích cho thời gian từ một ngày sinh đến hôm nay, nhưng tuổi pháp lý/thương mại vẫn phải tuân theo chính sách mà hệ thống cần áp dụng.

Một cách thiết kế tốt là tách rõ:

- **Khoảng lịch**: `Period.between(...)`, khi cần diễn giải năm/tháng/ngày.
- **Năm hoàn chỉnh theo quy tắc `Temporal`**: `ChronoUnit.YEARS.between(...)` cho nhu cầu tiêu chuẩn.
- **Tuổi theo ngày sinh có chính sách 29/02 riêng**: hàm `ageOn(...)` với `LeapDayPolicy`.

Đừng viết logic quan trọng theo cách người đọc phải đoán xem API mặc định xử lý ngày 29/02 ra sao. Đặt chính sách thành tham số/enum khiến quyết định dễ xem xét, kiểm thử và thay đổi.

## 8. Dùng “hôm nay” đúng múi giờ

`LocalDate.now()` sử dụng múi giờ mặc định của hệ thống. Nếu server chạy UTC trong khi ứng dụng phục vụ người dùng tại Việt Nam, thời điểm gần nửa đêm có thể khiến ngày “hôm nay” khác ngày trên đồng hồ người dùng.

Nên chọn vùng theo ngữ cảnh nghiệp vụ:

```java
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate todayForUser = LocalDate.now(userZone);

int userAge = ageOn(
        birthDate,
        todayForUser,
        LeapDayPolicy.FEBRUARY_28
);
```

Đây là đoạn mã trong phương thức có `import java.time.*;` và các biến đã được khai báo. Nếu tuổi được tính theo nơi cư trú, nơi thực hiện giao dịch hoặc quy tắc pháp lý, hãy lấy `ZoneId` phù hợp với miền nghiệp vụ đó. Đừng mặc định múi giờ máy chủ chính là múi giờ người dùng.

Đối với kiểm thử, có thể truyền ngày `asOf` tường minh như trong ví dụ `main` thay vì gọi `LocalDate.now()`. Điều này giúp test chạy giống nhau hôm nay, ngày mai và trên CI.

## 9. Ngày sinh không hợp lệ, giới hạn và kiểm tra đầu vào

### A. Từ chối ngày sinh trong tương lai

`ageOn` nên báo lỗi nếu `asOf.isBefore(birthDate)`. Với ứng dụng nhận dữ liệu người dùng, hãy kiểm tra ở biên nhận request và chuyển lỗi thành thông báo hữu ích; đừng trả về tuổi âm một cách âm thầm.

### B. Ngày 29/02 hợp lệ khi nào?

`LocalDate.of(2000, 2, 29)` hợp lệ; `LocalDate.of(1900, 2, 29)` và `LocalDate.of(2025, 2, 29)` không hợp lệ theo lịch ISO. Java ném `DateTimeException` nếu tạo ngày không tồn tại. Không nên tự động “sửa” ngày sinh sai, vì việc thay 29/02 thành 28/02 sẽ tạo một dữ liệu cá nhân khác.

### C. Không giả định chỉ có hai chính sách cho mọi nơi

Trong bài toán lập trình chung, hai lựa chọn 28/02 và 01/03 là những ví dụ rõ ràng. Nếu nghiệp vụ phải tuân theo luật địa phương, hợp đồng hoặc quy định riêng, hãy xác minh chính sách có hiệu lực; không xem enum ví dụ này là tư vấn pháp lý phổ quát.

### D. Ngày lịch khác thời điểm chính xác

Tuổi theo ngày sinh thông thường được tính từ các ngày lịch, vì vậy `LocalDate` là phù hợp. Nếu yêu cầu có độ chính xác thời điểm (ví dụ một mốc đúng 24 giờ trước ngày sinh), cần xác định vùng và thời điểm trước khi tính. Không chia chênh lệch mili giây cho một giá trị năm trung bình để quyết định tuổi, vì độ dài năm không cố định theo lịch.

## 10. Bộ kiểm thử biên nên có

Cho người sinh `2000-02-29`, test cả hai chính sách và các ngày sát sinh nhật:

| Ngày tính | Chính sách 28/02 | Chính sách 01/03 | Điều cần chứng minh |
| --- | ---: | ---: | --- |
| 2025-02-27 | 24 | 24 | Trước cả hai ngày quy ước. |
| 2025-02-28 | 25 | 24 | Khác biệt giữa hai chính sách. |
| 2025-03-01 | 25 | 25 | Cả hai đều đã đến sinh nhật quy ước. |
| 2024-02-28 | 23 | 23 | Năm nhuận, vẫn chưa tới ngày sinh. |
| 2024-02-29 | 24 | 24 | Đúng sinh nhật thật trong năm nhuận. |
| 2028-02-29 | 28 | 28 | Một năm nhuận sau đó. |

Ngoài ra, cần test người sinh ngày bình thường như `2000-06-20`: tuổi trước 20/06 phải ít hơn tuổi vào 20/06; các năm nhuận và năm không nhuận không làm thay đổi quy tắc sinh nhật bình thường. Test ngày tính trước ngày sinh phải ném lỗi theo thiết kế.

Khi viết unit test, truyền ngày cố định trực tiếp. Không cần `Thread.sleep`, không cần giả lập một khoảng thời gian, và không nên phụ thuộc vào ngày hiện tại của máy. Nếu hàm lấy hôm nay từ `Clock`, inject `Clock` cố định để có thể kiểm soát ngày trong kiểm thử.

## 11. Cách áp dụng trong ứng dụng

- **Hồ sơ người dùng:** lưu ngày sinh bằng `LocalDate`, vì ngày sinh không cần có giờ/phút.
- **Tính tuổi hiển thị trên hồ sơ:** truyền ngày hôm nay theo múi giờ sản phẩm hoặc người dùng, áp dụng chính sách 29/02 đã được chốt.
- **Tính tuổi trong quy trình quan trọng:** ghi rõ nguồn quy tắc (địa phương/pháp lý/hợp đồng) và tạo test biên cho cả 28/02, 29/02, 01/03.
- **Báo cáo có ngày chốt cố định:** dùng `ageOn(birthDate, reportingDate, policy)`. Không gọi “hôm nay” ở bên trong nếu báo cáo cần kết quả có thể tái lập.
- **API:** biểu diễn ngày sinh như chuỗi ISO `YYYY-MM-DD` hoặc kiểu ngày không giờ tương ứng; không buộc ngày sinh thành timestamp có múi giờ nếu không có ý nghĩa đó.
- **Cơ sở dữ liệu:** cột DATE thường phù hợp hơn timestamp có thời điểm; cấu hình ánh xạ cần theo driver và hệ quản trị thực tế.

Hãy đặt tên tham số `asOf` hoặc `calculationDate`, thay vì tên mơ hồ như `now` nếu giá trị thực chất là ngày báo cáo do người dùng chọn. Điều này giúp biểu thị rõ rằng hàm tính tuổi có thể được sử dụng cho quá khứ, hiện tại hoặc ngày đã định trong tương lai.

## 12. Lỗi thường gặp

1. **Chỉ lấy năm hiện tại trừ năm sinh.** Kết quả sai khi ngày sinh nhật của năm chưa đến.
2. **Bỏ qua 29/02 vào năm không nhuận.** Cần có một quy ước rõ ràng trước khi tính tuổi.
3. **Tự động dùng 28/02 hoặc 01/03 mà không xác nhận yêu cầu.** Hai quy tắc có thể cho kết quả tuổi khác nhau vào ngày 28/02.
4. **Cố tạo `LocalDate.of(year, 2, 29)` trong mọi năm.** Năm không nhuận sẽ ném `DateTimeException`; hãy dùng `Year.isLeap(year)` để chọn nhánh.
5. **Dùng `ChronoUnit.YEARS.between` như quy tắc duy nhất cho mọi nghiệp vụ.** API không biết chính sách 29/02 mà sản phẩm cần.
6. **Dùng `Duration` hoặc mili giây để chia thành năm.** Năm lịch không phải một số giây cố định; tuổi là một khái niệm theo lịch.
7. **Dùng múi giờ mặc định của server cho “hôm nay”.** Ngày có thể khác ở gần nửa đêm giữa server và người dùng; truyền `ZoneId` phù hợp.
8. **Không kiểm tra ngày tính trước ngày sinh.** Nếu không định nghĩa trường hợp này, hàm có thể đưa ra tuổi âm hoặc kết quả nghiệp vụ không hợp lệ.
9. **Gọi kết quả nhưng không lưu giá trị trả về.** `LocalDate` bất biến; các phép cộng/trừ lịch trả một đối tượng mới.
10. **Không test các ngày sát ranh giới.** Sai sót về tuổi thường nằm ở ngày ngay trước, chính ngày và ngày ngay sau sinh nhật.

## 13. Tự kiểm tra

**Câu 1.** Một người sinh `2000-06-20`, tính tuổi vào `2025-01-10`. Vì sao không phải 25?

**Đáp án:** Vì sinh nhật lần thứ 25 chưa đến trong năm 2025; tuổi hoàn chỉnh còn là 24.

**Câu 2.** Với người sinh `2000-02-29`, vào `2025-02-28`, chính sách 28/02 và 01/03 có thể cho hai kết quả nào?

**Đáp án:** Chính sách 28/02 trả 25; chính sách 01/03 trả 24.

**Câu 3.** Có nên dùng `LocalDate.of(2025, 2, 29)` để đại diện sinh nhật năm không nhuận?

**Đáp án:** Không. Ngày đó không tồn tại theo lịch ISO và Java ném `DateTimeException`. Hãy tạo ngày kỷ niệm theo chính sách.

**Câu 4.** Tại sao `Year.isLeap(2100)` là false, còn `Year.isLeap(2000)` là true?

**Đáp án:** Năm chia hết cho 100 không phải năm nhuận, trừ khi chia hết cho 400.

**Câu 5.** Có thể tính tuổi tại ngày báo cáo cố định hay không?

**Đáp án:** Có. Truyền `LocalDate` báo cáo làm `asOf` vào hàm; kết quả tái lập được và không phụ thuộc ngày hệ thống.

**Câu 6.** Nếu hệ thống chạy trên server UTC, người dùng đang ở Việt Nam, nên lấy ngày hiện tại bằng cách nào cho giao diện?

**Đáp án:** Chọn `ZoneId.of("Asia/Ho_Chi_Minh")` và gọi `LocalDate.now(zone)` khi quy tắc sản phẩm cần ngày địa phương Việt Nam.

## Ghi nhớ

**Tính tuổi bằng ngày lịch, không phải phép chia số mili giây.** Lấy hiệu hai năm, xác định sinh nhật trong năm xét rồi giảm một nếu ngày đang tính còn trước sinh nhật. Với người sinh ngày **29/02**, hãy xác định chính sách sinh nhật năm không nhuận là **28/02** hay **01/03** theo yêu cầu nghiệp vụ, mã hóa lựa chọn rõ ràng và kiểm thử ở hai ngày ranh giới. Dùng `LocalDate`, `Year.isLeap` và ngày tính `asOf` tường minh để kết quả đúng, dễ kiểm thử và không phụ thuộc múi giờ mặc định của server.
