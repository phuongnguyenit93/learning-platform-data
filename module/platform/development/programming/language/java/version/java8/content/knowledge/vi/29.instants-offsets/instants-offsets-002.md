# Epoch second, epoch milli và phần nanosecond trong Java Instant

## Mục tiêu

Cùng một mốc thời gian có thể được mô tả bằng số giây từ epoch, số mili giây từ epoch, hoặc cặp epoch-second + nano-of-second. Tuy nhiên, chúng **khác đơn vị và độ chính xác**. Nếu hiểu một giá trị mili giây là giây, thời điểm bị lệch rất lớn; nếu chỉ giữ mili giây, ta có thể làm mất dữ liệu dưới một mili giây.

Bài học giúp bạn:

1. Giải thích epoch Java là 1970-01-01T00:00:00Z.
2. Dùng đúng Instant.ofEpochSecond, Instant.ofEpochMilli, getEpochSecond, getNano và toEpochMilli.
3. Hiểu cấu trúc Instant là một long epoch-second và một int nano-of-second không âm.
4. Chuẩn hóa nanoAdjustment âm hoặc lớn hơn một tỷ.
5. Xử lý dữ liệu trước 1970 bằng Math.floorDiv/floorMod thay vì phép chia nguyên thiếu chính xác về ý nghĩa.
6. Phát hiện mất precision và overflow khi chuyển đổi timestamp.
7. Chọn cách lưu JSON/DB có hợp đồng về đơn vị và độ phân giải.
8. Không nhầm Instant với offset, System.nanoTime hoặc độ chính xác của clock vật lý.

**Phiên bản và Special Note:** java.time.Instant được giới thiệu từ Java 8 và vẫn còn áp dụng trong JDK hiện đại. Toàn bộ ví dụ độc lập bên dưới chạy trên Java 17+; khi dùng record (Java 16+), bài ghi rõ phiên bản. Không sử dụng API hay thói quen đã legacy.

## 1. Epoch và các đơn vị

Epoch là mốc 1970-01-01T00:00:00Z. Trong biểu diễn Java Instant, các mốc sau epoch có số dương, trước epoch có số âm.

| Thời điểm | Epoch-second | Epoch-milli |
|---|---:|---:|
| 1969-12-31T23:59:59Z | -1 | -1000 |
| 1969-12-31T23:59:59.999Z | -1 | -1 |
| 1970-01-01T00:00:00Z | 0 | 0 |
| 1970-01-01T00:00:00.001Z | 0 | 1 |
| 1970-01-01T00:00:01Z | 1 | 1000 |

Các hệ số cần nhớ: **1 giây = 1000 mili giây = 1.000.000 micro giây = 1.000.000.000 nano giây**. Một mili giây bằng một triệu nanosecond; một microsecond bằng một nghìn nanosecond.

Một con số như 1700000000 không tự nói nó là seconds hay milliseconds. Chỉ dựa vào số chữ số để đoán đơn vị không đáng tin, đặc biệt với dữ liệu lịch sử hoặc timestamp nhỏ trong unit test. Contract của nguồn phải định nghĩa đơn vị.

Epoch là mốc timeline, **không phải đồng hồ địa phương**. Khi đổi ZoneId/ZoneOffset để hiển thị, Instant và số epoch của nó không thay đổi.

## 2. Instant lưu hai thành phần

Theo JavaDoc, mô hình java.time.Instant gồm:

- **epochSecond**, kiểu long: số giây tính từ epoch.
- **nanoOfSecond**, kiểu int: số nano kể từ đầu giây, trong khoảng 0..999999999.

~~~text
Instant = (epochSecond: long, nanoOfSecond: int)
0 <= nanoOfSecond < 1_000_000_000

1970-01-01T00:00:03.123456789Z
  epochSecond=3
  nanoOfSecond=123456789

1969-12-31T23:59:59.999999999Z
  epochSecond=-1
  nanoOfSecond=999999999
~~~

Thời điểm thứ hai **chỉ trước epoch 1 nanosecond**, dù epochSecond=-1. Thành phần nano-of-second vẫn không âm. Nó không phải tổng số nanosecond từ 1970, cũng không phải phần nanosecond có dấu.

Công thức ý nghĩa toán học là epochSecond + nanoOfSecond/1.000.000.000 giây. **Đừng dùng double để lưu công thức ấy** khi cần độ chính xác tới nano, vì số thực dấu phẩy động không thể biểu diễn chính xác mọi nanosecond ở epoch lớn.

Instant là immutable, thread-safe và value-based. Sử dụng equals/compareTo để so hai Instant; không dựa vào reference identity hay synchronized trên một instance Instant.

## 3. Những API quan trọng

| API | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| Instant.EPOCH | Instant | Mốc 1970-01-01T00:00:00Z |
| Instant.ofEpochSecond(s) | long giây | Tạo thời điểm tại s giây, nano=0 |
| Instant.ofEpochSecond(s, nanoAdjustment) | hai long | Chuẩn hóa giây và phần nano điều chỉnh |
| Instant.ofEpochMilli(ms) | long mili giây | Tạo thời điểm theo epoch-millis |
| instant.getEpochSecond() | long giây | Thành phần giây chuẩn hóa |
| instant.getNano() | int nano | Thành phần nano từ 0 tới 999999999 |
| instant.toEpochMilli() | long mili giây | Có thể mất phần dưới 1 ms và overflow |
| instant.plusNanos(n) | Instant | Tạo thời điểm mới sau thêm n nano |
| instant.truncatedTo(MILLIS) | Instant | Cắt precision xuống milli |
| instant.atOffset(offset) | OffsetDateTime | Biểu diễn cùng timeline theo offset |
| instant.atZone(zone) | ZonedDateTime | Biểu diễn cùng timeline theo zone |

Hai dòng dưới có **cùng con số đầu vào nhưng khác thời điểm**:

~~~java
// Mảnh mã; cần import java.time.Instant.
Instant fromSeconds = Instant.ofEpochSecond(1_700_000_000L);
Instant fromMillis = Instant.ofEpochMilli(1_700_000_000L);
~~~

Factory không đoán đơn vị. Không truyền epoch seconds vào ofEpochMilli hoặc ngược lại.

## 4. Ví dụ đầy đủ 1 — so sánh seconds, millis và nanos

Tạo tệp **EpochUnitsDemo.java**:

~~~java
import java.time.Instant;

public class EpochUnitsDemo {
    public static void main(String[] args) {
        Instant precise = Instant.ofEpochSecond(
                1_700_000_000L, 123_456_789L);
        Instant millisOnly =
                Instant.ofEpochMilli(1_700_000_000_123L);
        Instant secondsOnly =
                Instant.ofEpochSecond(1_700_000_000L);

        System.out.println("precise=" + precise);
        System.out.println("epochSeconds=" + precise.getEpochSecond());
        System.out.println("nanoOfSecond=" + precise.getNano());
        System.out.println("epochMillis=" + precise.toEpochMilli());
        System.out.println("millisOnly=" + millisOnly);
        System.out.println("secondsOnly=" + secondsOnly);
        System.out.println("preciseEqualsMillis="
                + precise.equals(millisOnly));
        System.out.println("milliRoundTrip="
                + Instant.ofEpochMilli(millisOnly.toEpochMilli())
                        .equals(millisOnly));
    }
}
~~~

Chạy với JDK 17+:

~~~text
javac --release 17 EpochUnitsDemo.java
java EpochUnitsDemo
~~~

Stdout dự kiến:

~~~text
precise=2023-11-14T22:13:20.123456789Z
epochSeconds=1700000000
nanoOfSecond=123456789
epochMillis=1700000000123
millisOnly=2023-11-14T22:13:20.123Z
secondsOnly=2023-11-14T22:13:20Z
preciseEqualsMillis=false
milliRoundTrip=true
~~~

precise có phần nano 123456789, trong khi millisOnly chỉ có 123000000 nano. Hai Instant có thể có cùng epoch-milli mà vẫn khác nhau. Khi một Instant vốn đã chính xác tới mili giây, ofEpochMilli(toEpochMilli(...)) khôi phục được nó; điều này **không đúng với mọi Instant có fraction nano**.
## 5. NanoAdjustment: có thể âm hoặc vượt một tỷ

Tham số thứ hai của Instant.ofEpochSecond(long epochSecond, long nanoAdjustment) là **lượng điều chỉnh nanosecond**, không phải field nano-of-second cuối cùng. JDK cho phép nanoAdjustment âm hoặc lớn hơn 999999999, sau đó chuẩn hóa cả giây và nano.

~~~java
// Mảnh mã: cùng Instant, 3 giây và 1 nanosecond sau epoch.
Instant.ofEpochSecond(3, 1);
Instant.ofEpochSecond(4, -999_999_999);
Instant.ofEpochSecond(2, 1_000_000_001);
~~~

Ý tưởng chuẩn hóa:

~~~text
secondNormalized = s + floorDiv(n, 1_000_000_000)
nanoNormalized   = floorMod(n, 1_000_000_000)

0 <= nanoNormalized < 1_000_000_000
~~~

Dùng factory Java Time để kiểm tra phạm vi và overflow thay vì tự cộng long thiếu kiểm soát. Muốn tăng Instant 500 ns, dùng instant.plusNanos(500); còn with(ChronoField.NANO_OF_SECOND, value) là **thay field nano trong giới hạn hợp lệ**, không phải cộng nanosecond vượt ranh giới giây.

## 6. Epoch âm: vì sao phần nano vẫn không âm?

Một thời điểm trước epoch chỉ 1 ns:

~~~text
Instant.ofEpochSecond(0, -1)
= 1969-12-31T23:59:59.999999999Z

getEpochSecond() = -1
getNano() = 999999999
toEpochMilli() = -1
~~~

Cặp giây+nano đã chuẩn hóa là (-1, 999999999), **không phải** (0, -1). getNano không phải số nano có dấu.

Với epoch-milli âm, phép chia nguyên Java bằng / làm tròn **về 0**. Ví dụ:

~~~text
-1001 / 1000 = -1
Math.floorDiv(-1001, 1000) = -2
Math.floorMod(-1001, 1000) = 999

-1001 ms = -2 s + 999 ms
          = epochSecond=-2, nanoOfSecond=999000000
~~~

Khi cần tách milli âm thành cặp giây+nano, dùng floorDiv và floorMod:

~~~java
// Mảnh mã: epochMillis kiểu long.
long s = Math.floorDiv(epochMillis, 1000L);
long remainder = Math.floorMod(epochMillis, 1000L);
Instant restored = Instant.ofEpochSecond(
        s, remainder * 1_000_000L);
~~~

Nếu chỉ cần tạo Instant, gọi Instant.ofEpochMilli(epochMillis) trực tiếp. Không thay getEpochSecond bằng toEpochMilli()/1000 trong mọi trường hợp: với -1 ms, getEpochSecond=-1 nhưng phép chia long -1/1000=0.

## 7. Ví dụ đầy đủ 2 — chuẩn hóa và mốc trước epoch

Tạo file **NegativeEpochDemo.java**:

~~~java
import java.time.Instant;

public class NegativeEpochDemo {
    public static void main(String[] args) {
        Instant a = Instant.ofEpochSecond(3, 1);
        Instant b = Instant.ofEpochSecond(4, -999_999_999);
        Instant c = Instant.ofEpochSecond(2, 1_000_000_001);

        System.out.println("normalized=" + a);
        System.out.println("sameThree=" + (a.equals(b) && b.equals(c)));

        Instant before = Instant.ofEpochSecond(0, -1);
        System.out.println("before=" + before);
        System.out.println("before.seconds=" + before.getEpochSecond());
        System.out.println("before.nanos=" + before.getNano());
        System.out.println("before.millis=" + before.toEpochMilli());

        Instant negativeMilli = Instant.ofEpochMilli(-1001);
        System.out.println("negativeMilli=" + negativeMilli);
        System.out.println("negativeMilli.seconds="
                + negativeMilli.getEpochSecond());
        System.out.println("negativeMilli.nanos="
                + negativeMilli.getNano());

        long ms = -1001;
        long seconds = Math.floorDiv(ms, 1000L);
        long remainder = Math.floorMod(ms, 1000L);
        Instant rebuilt = Instant.ofEpochSecond(
                seconds, remainder * 1_000_000L);

        System.out.println("floorDiv=" + seconds);
        System.out.println("floorMod=" + remainder);
        System.out.println("rebuiltEquals=" + rebuilt.equals(negativeMilli));
        System.out.println("integerDiv=" + (ms / 1000L));
    }
}
~~~

Chạy:

~~~text
javac --release 17 NegativeEpochDemo.java
java NegativeEpochDemo
~~~

Stdout:

~~~text
normalized=1970-01-01T00:00:03.000000001Z
sameThree=true
before=1969-12-31T23:59:59.999999999Z
before.seconds=-1
before.nanos=999999999
before.millis=-1
negativeMilli=1969-12-31T23:59:58.999Z
negativeMilli.seconds=-2
negativeMilli.nanos=999000000
floorDiv=-2
floorMod=999
rebuiltEquals=true
integerDiv=-1
~~~

Ví dụ xác minh tham số nanoAdjustment có thể âm, nhưng phần getNano luôn không âm. Phần -1001 ms cần floorDiv=-2 để khớp cặp chuẩn hóa.
## 8. toEpochMilli làm mất độ phân giải dưới một mili giây

Một Instant có thể có phần nano tới 9 chữ số. Nhưng toEpochMilli trả long đơn vị mili giây, nên bỏ phần nhỏ hơn milli:

~~~text
2024-04-05T06:07:08.123456789Z
                  123 ms + 456789 ns dư

toEpochMilli() -> chỉ có tới 123 ms trong giây
ofEpochMilli(...) -> 2024-04-05T06:07:08.123Z
~~~

Độ chênh so với nguồn là **456789 ns**. Đây không phải cách làm tròn tới mili giây gần nhất.

### Timestamp âm: đừng làm tròn về 0 theo kiểu số thực

Với một Instant chỉ trước epoch 1 ns:

~~~text
Trước: 1969-12-31T23:59:59.999999999Z (-1 ns)
toEpochMilli() = -1
Sau:   1969-12-31T23:59:59.999Z (-1 ms)
~~~

Instant phục hồi sớm hơn nguồn **999999 ns**. Không giả lập toEpochMilli bằng ép kiểu double hoặc chia long theo hướng về 0; dùng API chuẩn và test riêng mốc âm.

### Khi cần cố ý hạ precision

- instant.truncatedTo(ChronoUnit.MILLIS) trả **Instant** được cắt phần dưới milli.
- instant.toEpochMilli() trả **long** với đơn vị milli.
- Instant.ofEpochMilli(ms) khôi phục mốc milli, không thể tái tạo phần nano đã mất.
- Muốn làm tròn theo quy tắc nghiệp vụ, viết rõ round-half-up, ceil hoặc floor theo contract thay vì mặc định toEpochMilli làm tròn gần nhất.

Hai Instant có cùng số epoch-milli vẫn có thể khác nhau, vì chúng có các phần nano dưới mili khác nhau.

## 9. Ví dụ đầy đủ 3 — mất nano và thay đổi thời điểm

Tạo file **PrecisionLossDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class PrecisionLossDemo {
    public static void main(String[] args) {
        Instant original = Instant.parse(
                "2024-04-05T06:07:08.123456789Z");
        long epochMillis = original.toEpochMilli();

        Instant fromMillis = Instant.ofEpochMilli(epochMillis);
        Instant truncated = original.truncatedTo(ChronoUnit.MILLIS);
        long remainderNanos =
                Duration.between(fromMillis, original).toNanos();

        System.out.println("original=" + original);
        System.out.println("fromMillis=" + fromMillis);
        System.out.println("truncated=" + truncated);
        System.out.println("equalAfterRoundTrip="
                + original.equals(fromMillis));
        System.out.println("truncatedMatches="
                + truncated.equals(fromMillis));
        System.out.println("lostNanos=" + remainderNanos);
        System.out.println("after500Nanos="
                + original.plusNanos(500));

        Instant tinyNegative = Instant.ofEpochSecond(0, -1);
        System.out.println("tinyNegative.milli="
                + tinyNegative.toEpochMilli());
        System.out.println("tinyNegative.roundTrip="
                + Instant.ofEpochMilli(tinyNegative.toEpochMilli()));
    }
}
~~~

Chạy:

~~~text
javac --release 17 PrecisionLossDemo.java
java PrecisionLossDemo
~~~

Stdout:

~~~text
original=2024-04-05T06:07:08.123456789Z
fromMillis=2024-04-05T06:07:08.123Z
truncated=2024-04-05T06:07:08.123Z
equalAfterRoundTrip=false
truncatedMatches=true
lostNanos=456789
after500Nanos=2024-04-05T06:07:08.123457289Z
tinyNegative.milli=-1
tinyNegative.roundTrip=1969-12-31T23:59:59.999Z
~~~

Phần .123456789 trở thành .123 sau khi qua milli; plusNanos tạo Instant mới, không sửa original. Với timestamp âm, chuyển thành milli có thể làm mốc khôi phục lệch về quá khứ gần một milli.

## 10. Epoch nanoseconds không phải getNano

getNano chỉ là số nano **bên trong giây**, lặp lại 0..999999999 ở mỗi giây. Ví dụ epochSecond=100 và nano=250000000 thì tổng epoch nanosecond là 100250000000, không phải 250000000.

Không lấy getNano riêng làm ID timestamp hoặc để so toàn bộ timeline. Cần giữ epochSecond.

Một long epoch-nanos có **miền thời gian ngắn hơn rất nhiều so với Instant**. Instant trong API cơ bản không cung cấp toEpochNano() trả long. Nếu tự tính:

~~~java
// PHẢN VÍ DỤ: phép toán long có thể overflow.
long total = instant.getEpochSecond() * 1_000_000_000L
        + instant.getNano();
~~~

thì số rất lớn có thể tràn im lặng. Với phạm vi long đã giới hạn, dùng Math.multiplyExact/Math.addExact để phát hiện overflow. Nếu cần số lớn hơn, dùng BigInteger hoặc lưu cặp seconds+nanos.

~~~java
// Mảnh mã, với import java.math.BigInteger.
BigInteger total = BigInteger.valueOf(
        instant.getEpochSecond())
        .multiply(BigInteger.valueOf(1_000_000_000L))
        .add(BigInteger.valueOf(instant.getNano()));
~~~

BigInteger cho phép tổng epoch nanos âm trước 1970 và không overflow như long. Đừng lẫn tổng epoch nanos với nanoAdjustment mà Instant.ofEpochSecond chấp nhận.
## 11. Khi cần round-trip chính xác, lưu seconds + nanos

Một cấu trúc dữ liệu minh bạch là:

~~~text
epochSecond: long
nanoOfSecond: int (0..999999999)
~~~

Nó giữ đủ phần fraction và không làm mất thời điểm âm. Đối với Java 17+, record là một kiểu DTO gọn:

~~~java
// Mảnh mã Java 17+; cần import java.time.Instant.
record EpochParts(long seconds, int nanos) {
    EpochParts {
        if (nanos < 0 || nanos >= 1_000_000_000) {
            throw new IllegalArgumentException("invalid nanos");
        }
    }
    Instant toInstant() {
        return Instant.ofEpochSecond(seconds, nanos);
    }
    static EpochParts from(Instant instant) {
        return new EpochParts(instant.getEpochSecond(), instant.getNano());
    }
}
~~~

**Nanos của DTO là nano-of-second đã chuẩn hóa**, không phải nanoAdjustment có dấu. Nếu nguồn gửi nanoAdjustment âm, tạo Instant qua ofEpochSecond rồi lấy getEpochSecond/getNano để đưa về chuẩn trước khi lưu.

| Tiêu chí | Cặp seconds+nanos | Một long epoch-millis |
|---|---|---|
| Độ phân giải | Nanosecond | Millisecond |
| Số field | 2 | 1 |
| Khôi phục Instant có phần dưới milli | Có | Không |
| Thời điểm trước 1970 | Seconds âm, nanos không âm | Số milli có dấu |
| Phạm vi | Miền Instant | Bị giới hạn long milli |
| Lỗi thường gặp | Nanos âm/không chuẩn hóa | Nhầm seconds/millis, mất precision |

Khi một giao thức khác cũng dùng hai field seconds+nanos, vẫn phải kiểm tra hợp đồng về giới hạn năm, phạm vi số, leap seconds và định nghĩa field. Không mặc định mọi kiểu Timestamp giống hệt java.time.Instant.

### Khi cần đặt dữ liệu vào DB hoặc JSON

Đừng lưu cả seconds, nanos và millis như ba nguồn sự thật độc lập nếu thiếu quy tắc đồng bộ hóa; millis có thể không khớp do mất phần fraction. Chọn một dạng canonical và tạo dạng khác khi cần.

Khi một backend yêu cầu timestamp chính xác tới nano nhưng database chỉ có độ phân giải microsecond, cần chọn schema/encoding phù hợp hoặc chấp nhận mất precision theo hợp đồng rõ ràng. Test round-trip với fraction .123456789 và các mốc âm, thay vì chỉ test thời điểm tròn giây.

## 12. Ví dụ đầy đủ 4 — record và BigInteger

Tạo file **EpochPartsDemo.java**:

~~~java
import java.math.BigInteger;
import java.time.Instant;

public class EpochPartsDemo {
    record EpochParts(long seconds, int nanos) {
        EpochParts {
            if (nanos < 0 || nanos >= 1_000_000_000) {
                throw new IllegalArgumentException(
                        "nanos out of range");
            }
        }

        Instant toInstant() {
            return Instant.ofEpochSecond(seconds, nanos);
        }

        static EpochParts from(Instant instant) {
            return new EpochParts(
                    instant.getEpochSecond(), instant.getNano());
        }

        BigInteger epochNanoseconds() {
            return BigInteger.valueOf(seconds)
                    .multiply(BigInteger.valueOf(1_000_000_000L))
                    .add(BigInteger.valueOf(nanos));
        }
    }

    public static void main(String[] args) {
        Instant source = Instant.ofEpochSecond(0, -1);
        EpochParts fields = EpochParts.from(source);

        System.out.println("parts=" + fields);
        System.out.println("roundTrip=" + fields.toInstant());
        System.out.println("equal=" + source.equals(fields.toInstant()));
        System.out.println("epochNanos=" + fields.epochNanoseconds());

        EpochParts positive = EpochParts.from(
                Instant.ofEpochSecond(100, 250_000_000));
        System.out.println("positiveNanos="
                + positive.epochNanoseconds());

        try {
            new EpochParts(3, -1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidParts=IllegalArgumentException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 EpochPartsDemo.java
java EpochPartsDemo
~~~

Stdout:

~~~text
parts=EpochParts[seconds=-1, nanos=999999999]
roundTrip=1969-12-31T23:59:59.999999999Z
equal=true
epochNanos=-1
positiveNanos=100250000000
invalidParts=IllegalArgumentException
~~~

Dù total epoch nanos là -1, phần nanos trong DTO vẫn không âm. Record validate dữ liệu trước khi lưu; BigInteger giúp tính tổng nanos chính xác mà không phụ thuộc vào giới hạn 64-bit cho toàn bộ miền Instant.

## 13. Overflow và giới hạn miền thời gian

Java Instant có miền ngày giờ rất rộng nhưng **không phải mọi Instant đều biểu diễn được bằng long epoch-milli**. Cần phân biệt:

- **Instant.ofEpochSecond(Long.MAX_VALUE)**: đầu vào có kiểu long hợp lệ nhưng nằm ngoài phạm vi Instant, ném DateTimeException.
- **Instant.ofEpochSecond(s, nanoAdjustment)**: có thể ném DateTimeException khi vượt miền Instant hoặc ArithmeticException nếu tính toán số học overflow.
- **Instant.MAX.toEpochMilli()**: số milli không vừa long, ném ArithmeticException.
- Phép nhân seconds * 1000 hoặc seconds * 1_000_000_000 trong long có thể **tràn mà không báo lỗi**.
- **Math.multiplyExact** và **Math.addExact** phát hiện overflow nếu bạn cần làm số học trong long.

Đừng dùng Instant.MAX.toEpochMilli() như cách tìm milli tối đa hợp lệ. Đừng cho rằng parser chấp nhận một long epochSecond là đủ chứng minh giá trị đó tạo được Instant; phải validate bằng factory Java Time.

Đối với thuật toán tính thời lượng giữa hai mốc xa nhau, các API trả long nanos cũng có thể không chứa hết phạm vi. Cần xem contract Duration/ChronoUnit và sử dụng BigInteger hoặc thay cách biểu diễn khi cần.
## 14. Clock, precision và đo thời lượng

Instant có thành phần nanosecond, nhưng **khả năng biểu diễn đến nano không đồng nghĩa đồng hồ vật lý chính xác 1 ns**. Clock.systemUTC và Instant.now có thể dựa trên nguồn hệ thống có độ phân giải hữu hạn hoặc bị điều chỉnh.

Trong unit test, dùng Clock.fixed để có timestamp xác định:

~~~java
// Mảnh mã, cần import java.time.*.
Clock clock = Clock.fixed(
        Instant.parse("2024-01-01T00:00:00.123456789Z"),
        ZoneOffset.UTC);
Instant now = Instant.now(clock);
~~~

Clock.fixed trả cùng một Instant trong mọi lần gọi. ZoneOffset.UTC chỉ là cách diễn giải ngày giờ khi dùng Clock với LocalDate/LocalTime; bản thân Instant không lưu múi giờ.

### currentTimeMillis và nanoTime không giống nhau

| API | Kết quả | Dùng khi nào |
|---|---|---|
| System.currentTimeMillis() | Long mili giây từ epoch theo clock hệ thống | Timestamp milli thô |
| Instant.now(clock) | Một Instant, có seconds + nanos | Mốc event/deadline |
| System.nanoTime() | Nano tính từ mốc **tùy ý**, không phải epoch | Đo elapsed time giữa hai lần gọi |
| Duration.between(a,b) | Thời lượng giữa hai mốc | Khi hai Instant phản ánh đúng timeline |

Dù tên có chữ nano, **System.nanoTime không phải Unix nanoseconds**. Không truyền nó vào API chờ một timestamp UTC. Khi đo thời gian chạy chương trình trong một tiến trình, dùng hiệu hai lần nanoTime, không diễn giải một giá trị riêng thành ngày tháng.

System.nanoTime phù hợp đo elapsed time; Instant.now dựa trên wall clock không được bảo đảm monotonic. Clock vật lý có thể bị điều chỉnh, và độ chính xác thực còn phụ thuộc hệ điều hành, NTP, phần cứng.

## 15. Ví dụ đầy đủ 5 — kiểm tra Clock và overflow

Tạo file **EpochRangeAndClockDemo.java**:

~~~java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.ZoneOffset;

public class EpochRangeAndClockDemo {
    public static void main(String[] args) {
        Instant source = Instant.parse(
                "2024-01-01T00:00:00.123456789Z");
        Clock fixed = Clock.fixed(source, ZoneOffset.UTC);
        Instant measured = Instant.now(fixed);

        System.out.println("clockInstant=" + measured);
        System.out.println("clockNanos=" + measured.getNano());
        System.out.println("clockMillis=" + measured.toEpochMilli());

        try {
            Instant.MAX.toEpochMilli();
        } catch (ArithmeticException expected) {
            System.out.println("maxMillis=ArithmeticException");
        }

        try {
            Instant.ofEpochSecond(Long.MAX_VALUE);
        } catch (DateTimeException expected) {
            System.out.println("hugeSeconds=DateTimeException");
        }

        try {
            Math.multiplyExact(Long.MAX_VALUE, 1000L);
        } catch (ArithmeticException expected) {
            System.out.println("multiply=ArithmeticException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 EpochRangeAndClockDemo.java
java EpochRangeAndClockDemo
~~~

Stdout:

~~~text
clockInstant=2024-01-01T00:00:00.123456789Z
clockNanos=123456789
clockMillis=1704067200123
maxMillis=ArithmeticException
hugeSeconds=DateTimeException
multiply=ArithmeticException
~~~

Clock.fixed giúp stdout xác định; bài không hứa một đồng hồ thật có 9 chữ số nano chính xác. Ví dụ cũng chứng minh một long hợp lệ chưa chắc là epoch-second hợp lệ và một Instant hợp lệ chưa chắc chuyển được sang epoch-milli.

## 16. Epoch second không đổi khi thay offset hoặc zone

Instant đại diện một thời điểm trên timeline. Muốn hiển thị nó theo Việt Nam hay Paris, dùng **atOffset** hoặc **atZone**:

~~~java
// Mảnh mã.
Instant event = Instant.parse("2024-06-01T02:30:15.123456789Z");
OffsetDateTime vietnam = event.atOffset(ZoneOffset.ofHours(7));
ZonedDateTime paris = event.atZone(ZoneId.of("Europe/Paris"));
~~~

Hai cách hiển thị có cùng **toInstant()**, **getEpochSecond** và **getNano** như event. Chỉ phần ngày giờ địa phương và offset khác nhau.

**Phản ví dụ:** event.plusSeconds(7 * 3600) **không** phải là cách đổi hiển thị sang UTC+07. Nó tạo một Instant mới muộn hơn bảy giờ, thay đổi chính sự kiện.

Nếu chỉ có LocalDateTime, chưa thể suy ra epoch-second vì thiếu offset/zone:

~~~java
// Mảnh mã.
LocalDateTime local =
        LocalDateTime.of(2024, 6, 1, 9, 30, 15, 123_456_789);
ZoneOffset offset = ZoneOffset.ofHours(7);

long seconds = local.toEpochSecond(offset);
Instant instant = local.toInstant(offset);
~~~

toEpochSecond(offset) trả long **chỉ đến đơn vị giây**, không mang theo nanos. toInstant(offset) giữ fraction. Nếu ngữ cảnh là một khu vực địa lý có DST, cần dùng ZoneId và chọn quy tắc cho gap/overlap thay vì gắn một offset đoán mò.

## 17. Ví dụ đầy đủ 6 — cùng epoch, khác đồng hồ

Tạo file **OffsetAndEpochDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class OffsetAndEpochDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse(
                "2024-06-01T02:30:15.123456789Z");

        OffsetDateTime vietnam =
                event.atOffset(ZoneOffset.ofHours(7));
        ZonedDateTime paris =
                event.atZone(ZoneId.of("Europe/Paris"));

        System.out.println("event=" + event);
        System.out.println("vietnam=" + vietnam);
        System.out.println("paris=" + paris);
        System.out.println("sameInstant="
                + (event.equals(vietnam.toInstant())
                    && event.equals(paris.toInstant())));

        LocalDateTime local = LocalDateTime.of(
                2024, 6, 1, 9, 30, 15, 123_456_789);
        ZoneOffset plusSeven = ZoneOffset.ofHours(7);

        System.out.println("converted=" + local.toInstant(plusSeven));
        System.out.println("secondsEqual="
                + (local.toEpochSecond(plusSeven)
                    == event.getEpochSecond()));
        System.out.println("nanosPreserved="
                + (local.toInstant(plusSeven).getNano()
                    == event.getNano()));
    }
}
~~~

Chạy:

~~~text
javac --release 17 OffsetAndEpochDemo.java
java OffsetAndEpochDemo
~~~

Stdout:

~~~text
event=2024-06-01T02:30:15.123456789Z
vietnam=2024-06-01T09:30:15.123456789+07:00
paris=2024-06-01T04:30:15.123456789+02:00[Europe/Paris]
sameInstant=true
converted=2024-06-01T02:30:15.123456789Z
secondsEqual=true
nanosPreserved=true
~~~

Một Instant có thể được thể hiện dưới nhiều offset/zone mà không đổi epoch-second và nano-of-second. LocalDateTime cần offset hợp lệ mới chuyển thành Instant; với offset đó, phần nano vẫn được toInstant bảo toàn.
## 18. Chuỗi ISO có phần fraction: đọc đúng 3, 6 và 9 chữ số

Các chuỗi sau đều có dạng ISO-8601 của một Instant nhưng khác fraction:

~~~text
2024-01-01T00:00:00Z
2024-01-01T00:00:00.123Z
2024-01-01T00:00:00.123456Z
2024-01-01T00:00:00.123456789Z
~~~

| Fraction trong chuỗi | getNano() |
|---|---:|
| Không có | 0 |
| .123 | 123000000 |
| .123456 | 123456000 |
| .123456789 | 123456789 |

**Chuỗi .123 nghĩa là 123 mili giây, không phải 123 nanosecond.** Số chữ số của fraction xác định trọng số của phần thập phân. Instant.toString có thể in 0, 3, 6 hoặc 9 chữ số fraction tùy dữ liệu, không hứa luôn có đủ 9 số. Độ dài chuỗi in ra không chứng minh độ phân giải vật lý của clock.

Khi format timestamp chỉ tới milli, dữ liệu micro/nano có thể bị cắt. Nếu cần round-trip giữ chính xác, sử dụng chuỗi ISO có đầy đủ fraction hoặc cặp seconds+nanos. Không truyền timestamp epoch seconds với phần fraction thông qua double khi bài toán yêu cầu chính xác đến nano: IEEE-754 double có giới hạn precision.

### So sánh với Duration

Duration.between(a,b) giúp tính elapsed time giữa hai Instant. Nhưng phép đổi toàn bộ Duration sang long nanos có thể overflow nếu thời lượng quá lớn; không dùng nó thay một BigInteger epoch-nanos không giới hạn. Lưu ý Duration và Instant có kiểu dữ liệu khác nhau: Duration là **khoảng thời gian**, Instant là **một mốc**.

## 19. Hợp đồng JSON và database

Các payload sau có precision khác nhau:

~~~json
{
  "epochSecond": 1700000000,
  "nanoOfSecond": 123456789
}
~~~

~~~json
{
  "epochMillis": 1700000000123
}
~~~

Payload đầu đủ phần nano; payload thứ hai chỉ giữ milli. Khi thiết kế API, phải quy định:

1. Field đo theo seconds, milliseconds, microseconds hay nanoseconds?
2. Mốc bắt đầu là Unix epoch 1970-01-01T00:00:00Z hay mốc khác?
3. Có chấp nhận timestamp âm và khoảng giá trị nào?
4. nanoOfSecond là field **0..999999999**, hay một nanoAdjustment tùy ý cần chuẩn hóa?
5. Có cắt, làm tròn hoặc từ chối fraction không đúng precision?
6. Client có thể đọc/ghi toàn bộ số long mà không mất chữ số không?

Ví dụ frontend dùng JavaScript Number chỉ biểu diễn chính xác số nguyên trong một miền hữu hạn; một long quá lớn có thể mất bit thấp. Khi cần full 64-bit, chọn chuỗi số hoặc cơ chế serialization có contract phù hợp.

### Kiểu cột thời gian không tự bảo đảm nanosecond

Một cột SQL tên TIMESTAMP không cho biết chắc nó lưu Instant hay LocalDateTime, lưu milli, micro hay nano, hoặc giữ ZoneId ban đầu. Nhiều database và driver chỉ hỗ trợ một phần fraction. Nếu ghi giá trị .123456789 rồi đọc lại .123456, bạn đã mất 789 ns.

Hãy kiểm tra schema/driver thật và viết test round-trip với mốc âm cùng timestamp 9 chữ số fraction. Một số ứng dụng có thể **chấp nhận** độ phân giải milli/micro, nhưng đó phải là quyết định có chủ đích, không phải tác dụng phụ của việc chọn toEpochMilli.

### Log và event ordering

Hai event khác nhau có thể cùng số epoch-milli. Ngay cả hai lần Instant.now() cũng có thể trả cùng timestamp nếu clock không đủ độ phân giải. Nếu cần một thứ tự tuyệt đối của sự kiện, có thể cần sequence ID, monotonic sequence hoặc protocol ordering riêng, chứ không chỉ dựa vào timestamp.

Đừng dùng getNano() làm ID độc nhất: giá trị 0..999999999 lặp lại mỗi giây.

## 20. Lỗi phổ biến cần tránh

### 20.1. Trộn giây và mili giây

~~~java
// PHẢN VÍ DỤ: biến epochSeconds thật ra là đơn vị giây.
Instant wrong = Instant.ofEpochMilli(epochSeconds);
~~~

Đúng là Instant.ofEpochSecond(epochSeconds). Đặt tên biến có đơn vị để giảm lỗi.

### 20.2. Làm mất nano khi cần round-trip

~~~java
// PHẢN VÍ DỤ khi original chứa sub-milli.
Instant restored = Instant.ofEpochMilli(original.toEpochMilli());
~~~

Nếu cần giữ đủ precision, dùng cặp seconds+nanos hoặc encoding ISO giữ đủ fraction.

### 20.3. Gán nanos âm vào DTO đã chuẩn hóa

Instant.ofEpochSecond(0,-1) nhận nanoAdjustment âm, nhưng cặp dữ liệu trả ra là (-1,999999999). Không lưu nanos=-1 dưới tên nanoOfSecond.

### 20.4. Chia epoch milli âm bằng toán tử /

Phép chia nguyên Java làm tròn về 0; không luôn khớp getEpochSecond. Sử dụng floorDiv/floorMod hoặc factory Instant.ofEpochMilli.

### 20.5. Cho rằng toEpochMilli làm tròn gần nhất

Nó bỏ phần nhỏ hơn 1 ms theo contract. Test timestamp âm như -1 ns, nơi số milli là -1 thay vì 0.

### 20.6. Tự nhân seconds với một tỷ không kiểm tra overflow

Không có long nào lưu toàn bộ miền epoch-nanos của Instant. Dùng Math.multiplyExact/BigInteger nếu cần tính tổng nano.

### 20.7. Dùng System.nanoTime như timestamp Unix

System.nanoTime dành cho elapsed time tương đối; nó không chứa epoch date. Dùng Instant.now(clock) hoặc API cung cấp epoch milli khi cần mốc tuyệt đối.

### 20.8. Cộng offset vào Instant khi chỉ muốn hiển thị giờ địa phương

Cộng offset làm thay đổi Instant. Dùng atOffset/atZone để giữ nguyên mốc timeline.

### 20.9. Coi 9 chữ số nano là bằng chứng đồng hồ có precision 1 ns

Instant biểu diễn được nano, nhưng clock thật có giới hạn độ phân giải và độ chính xác. Sử dụng Clock.fixed để test.

### 20.10. Gọi Instant.MAX.toEpochMilli rồi kỳ vọng long hợp lệ

Miền Instant rộng hơn miền epoch milli 64-bit. toEpochMilli có thể ném ArithmeticException.

## 21. Checklist thực hành

- Field có ghi rõ unit seconds/millis/micros/nanos?
- Nghiệp vụ có cần phân biệt các event cách nhau dưới 1 ms?
- Timestamp có thể âm trước 1970 không?
- nanos là nano-of-second không âm hay nanoAdjustment cần chuẩn hóa?
- Đã dùng floorDiv/floorMod khi phân tách epoch milli âm?
- Có phát hiện overflow khi nhân đơn vị hoặc chuyển Instant rất xa thành epoch milli?
- Có hiểu System.nanoTime khác epoch time?
- Khi hiển thị vùng khác, có giữ cùng Instant không?
- JSON/DB serializer có giữ 9 chữ số fraction nếu cần không?
- Test có kiểm tra đồng thời trường hợp ngay trước epoch, fraction 9 số và phạm vi lớn không?

## 22. Bài tập tự kiểm tra

**Câu 1.** Epoch-second 1 và epoch-milli 1 có khác nhau không?

*Đáp án:* Có. Thứ nhất là 1 giây sau epoch; thứ hai là 1 mili giây sau epoch.

**Câu 2.** Instant.ofEpochSecond(1,500000000) biểu diễn gì?

*Đáp án:* 1970-01-01T00:00:01.500Z.

**Câu 3.** ofEpochSecond(0,-1) có getEpochSecond và getNano bao nhiêu?

*Đáp án:* -1 và 999999999, dù chỉ trước epoch một nanosecond.

**Câu 4.** ofEpochMilli(-1) có nano âm không?

*Đáp án:* Không. epochSecond=-1 và nanoOfSecond=999000000.

**Câu 5.** Hai Instant có cùng epoch-milli có chắc equals không?

*Đáp án:* Không. Chúng có thể khác phần sub-milli.

**Câu 6.** Vì sao Math.floorDiv cần thiết khi tách epoch-milli âm?

*Đáp án:* Vì chia long thông thường làm tròn về 0, còn cặp seconds/nanos của Instant được chuẩn hóa với nanos không âm.

**Câu 7.** Instant.ofEpochSecond(3,1) và Instant.ofEpochSecond(2,1000000001) có bằng nhau không?

*Đáp án:* Có, nanoAdjustment được chuẩn hóa.

**Câu 8.** System.nanoTime dùng làm Unix nanoseconds trong JSON được không?

*Đáp án:* Không. Nó là bộ đếm tương đối dành cho đo thời lượng.

**Câu 9.** Nếu lưu một Instant chính xác tới nano vào long epoch-milli, làm thế nào khôi phục đầy đủ?

*Đáp án:* Không thể nếu đã bỏ sub-milli. Phải lưu thêm nano hoặc giữ một biểu diễn chính xác khác từ đầu.

**Câu 10.** Cộng 7 giờ vào Instant có phải đổi hiển thị sang giờ Việt Nam không?

*Đáp án:* Không. Nó làm thay đổi sự kiện trên timeline. Dùng atOffset(+07:00) hoặc atZone.

## Tài liệu chính thức hiện hành

- Oracle Java SE 25 — Instant: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html
- Oracle Java SE 25 — Clock: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html
- Oracle Java SE 25 — Duration: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html
- Oracle Java SE 25 — ZoneOffset: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneOffset.html
- Oracle Java SE 25 — OffsetDateTime: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html
- Oracle Java SE 25 — ChronoField: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/ChronoField.html
- Oracle Java SE 25 — ChronoUnit: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/ChronoUnit.html

**Kết luận:** Instant là mốc trên timeline với cặp **epochSecond và nanoOfSecond không âm**. Một long epoch-milli thuận tiện nhưng có thể làm mất phần dưới milli và có giới hạn phạm vi. Với timestamp âm, cần chuẩn hóa bằng floorDiv/floorMod; với độ chính xác cao, lưu đủ seconds+nanos. Ghi rõ đơn vị/precision trong mọi API và tránh nhầm offset hiển thị với phép cộng thời gian.