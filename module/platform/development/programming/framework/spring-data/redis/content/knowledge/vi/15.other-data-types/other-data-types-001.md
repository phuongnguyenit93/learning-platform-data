# Bitmap: đặt bit, đọc bit và đếm số bit được bật

Redis có thể lưu trạng thái **bật/tắt** cho rất nhiều đối tượng bằng cách dùng từng bit của một giá trị String. Cách biểu diễn này thường được gọi là **Redis Bitmap**. Ví dụ, trong một ngày, ứng dụng muốn biết những tài khoản nào đã đăng nhập: mỗi tài khoản được gán một vị trí bit cố định; khi đăng nhập, ứng dụng đặt bit tại vị trí đó thành `1`. Sau đó có thể kiểm tra một tài khoản bằng `GETBIT` hoặc đếm tổng số vị trí đang bật bằng `BITCOUNT`.

Trong Spring Data Redis, các thao tác này có thể được gọi qua `StringRedisTemplate` / `ValueOperations` và, với một số lệnh cấp thấp, qua `RedisConnection`. Bitmap rất hiệu quả khi ID có thể ánh xạ thành **vị trí số nguyên tương đối dày đặc**, nhưng cũng có các giới hạn dễ bỏ qua: **Redis Bitmap thực chất là Redis String**, byte có thể được cấp phát tới vị trí bit cao nhất, không có thứ tự thành viên hay TTL theo từng bit, và `BITCOUNT` phải quét nội dung chứ không phải phép đếm hằng số thời gian.

Bài học đi từ cách lưu bit, nguyên tắc đánh số, ví dụ Redis CLI, mã Java Spring Boot, đến các lựa chọn thiết kế dữ liệu và chi phí vận hành khi có rất nhiều người dùng.

## 1. Redis Bitmap là gì?

Về mặt kiểu dữ liệu Redis, **không có kiểu `bitmap` độc lập** giống như Set hoặc Hash. Một bitmap dùng **Redis String** làm vùng byte, với các lệnh thao tác theo từng bit:

- `SETBIT key offset value`: đặt bit ở vị trí `offset` thành `0` hoặc `1`.
- `GETBIT key offset`: đọc giá trị bit ở vị trí `offset`.
- `BITCOUNT key`: đếm tổng số bit `1` trong toàn bộ chuỗi byte.
- Các lệnh liên quan như `BITPOS`, `BITOP` và `BITFIELD` có thể hữu ích trong những bài toán mở rộng.

Ví dụ các vị trí bit của key `active:2026-11-12`:

```text
  Offset:      0  1  2  3  4  5  6  7 | 8  9  10 11 12 13 14 15
  Bit:         0  1  0  1  0  0  1  0 | 0  0   0  0  0  0  0  0
              └──────── Byte 0 ──────┘ └──────── Byte 1 ───────┘

  Member đang bật: offset 1, 3, 6
  BITCOUNT = 3
```

Mỗi offset biểu diễn một **định danh số** hoặc một trạng thái boolean do ứng dụng quy ước. Redis không hiểu bit số 3 là tài khoản nào: Spring Boot, database hoặc hệ thống ID phải bảo đảm việc ánh xạ giữa **đối tượng nghiệp vụ ↔ offset** luôn đúng.

### Vì sao Bitmap tiết kiệm bộ nhớ?

Theo biểu diễn bit thuần túy, tối đa tám trạng thái nhị phân được đặt trong một byte:

\\[
\\text{Dung lượng payload lý tưởng (byte)} =
\\left\\lceil \\frac{N}{8} \\right\\rceil
\\]

Trong đó `N` là số **vị trí bit cần biểu diễn**, tính từ offset `0`. Một triệu vị trí tương ứng khoảng `1.000.000 / 8 = 125.000` byte (~122 KiB) payload; mười triệu vị trí tương ứng khoảng 1,25 MB payload. Đây **chưa** phải tổng bộ nhớ Redis dùng cho key, vì còn overhead của object, allocator và các cấu trúc nội bộ.

Sự tiết kiệm này chỉ đúng khi **không gian offset tương đối dày đặc**. Nếu chỉ có một user tại offset `100.000.000`, Redis vẫn phải có đủ byte để biểu diễn từ vị trí đầu tiên tới offset ấy; payload có thể hơn 12,5 MB dù **chỉ một bit** bằng `1`.

## 2. Hiểu bit offset trước khi viết code

**Offset** là một số nguyên không âm biểu diễn vị trí bit. Redis đánh số từ `0`. Với byte đầu tiên, offset `0` là **bit có trọng số cao nhất (most significant bit)**, offset `7` là bit thấp nhất; offset `8` bắt đầu byte thứ hai.

```text
Offset:       0 1 2 3 4 5 6 7
Byte đầu:    1 0 0 0 0 0 0 1  = 10000001 (nhị phân)
                                      = 0x81 (hex)
```

Với một offset `i`:

\\[
\\text{byteIndex} = \\left\\lfloor \\frac{i}{8} \\right\\rfloor
\\]

\\[
\\text{bitPositionFromMSB} = i \\bmod 8
\\]

Nếu cần thao tác trực tiếp trên byte, bit theo trọng số từ thấp lên có vị trí `7 − (i mod 8)`. Trong ứng dụng Spring Data Redis, **không cần tự dịch bit** khi dùng `SETBIT`/`GETBIT`, vì Redis xử lý bit offset theo quy ước của server.

### Ví dụ đặt những bit đầu tiên

```redis
SETBIT demo:bitmap 0 1
# 0: giá trị cũ ở bit 0 là 0

SETBIT demo:bitmap 7 1
# 0: giá trị cũ ở bit 7 là 0

GETBIT demo:bitmap 0
# 1

GETBIT demo:bitmap 1
# 0

GETBIT demo:bitmap 7
# 1

BITCOUNT demo:bitmap
# 2

STRLEN demo:bitmap
# 1 (byte)

TYPE demo:bitmap
# string
```

Ở ví dụ này, byte đầu tiên có giá trị nhị phân `10000001`. `TYPE` trả về `string` vì bitmap là cách **sử dụng Redis String**, không phải một Redis data type riêng.

### Giá trị của `SETBIT` và kết quả trả về

```redis
SETBIT demo:flag 5 1
# 0

SETBIT demo:flag 5 1
# 1

SETBIT demo:flag 5 0
# 1

GETBIT demo:flag 5
# 0
```

`SETBIT` trả về **giá trị cũ tại vị trí bit**, không phải “số bit mới được thêm” và cũng không phải `OK`:

| Giá trị cũ | Giá trị muốn ghi | Kết quả trả về | Giá trị cuối |
| --- | --- | --- | --- |
| `0` | `1` | `0` | `1` |
| `1` | `1` | `1` | `1` |
| `1` | `0` | `1` | `0` |
| `0` | `0` | `0` | `0` |

Nhờ vậy, nếu ứng dụng đặt bit thành `1` và lệnh trả giá trị cũ `0`, ứng dụng biết **đây là lần chuyển từ chưa bật sang bật** tại thời điểm server xử lý lệnh. Nhưng điều đó **không** tự chứng minh đối tượng được ghi lần đầu trong toàn bộ lịch sử: key có thể đã hết TTL, bị xóa, hoặc bị tác vụ khác đặt bit về `0` trước đó.

## 3. Các lệnh Redis Bitmap quan trọng

| Lệnh | Ý nghĩa | Độ phức tạp điển hình | Ghi chú |
| --- | --- | --- | --- |
| `SETBIT key offset 0/1` | Đặt một bit, trả bit cũ | `O(1)` cho thao tác bit; tạo string lớn lần đầu có thể có chi phí cấp phát đáng kể | Có thể tạo key khi chưa tồn tại |
| `GETBIT key offset` | Đọc một bit | `O(1)` | Vị trí chưa có trong chuỗi được xem là `0` |
| `BITCOUNT key` | Đếm tất cả bit `1` | `O(N)` theo số byte cần quét | Không phải bộ đếm được Redis duy trì sẵn |
| `BITCOUNT key start end` | Đếm bit `1` trong đoạn byte | `O(N)` theo phần byte được chỉ định | Theo cú pháp mặc định, `start/end` là **vị trí byte** |
| `BITPOS key bit` | Tìm vị trí xuất hiện của bit `0` hoặc `1` | Phụ thuộc lượng dữ liệu cần quét | Chú ý đặc điểm của vùng bit `0` chưa được cấp phát |
| `BITOP AND/OR/XOR/NOT` | Kết hợp bit giữa các String | Phụ thuộc chiều dài chuỗi lớn nhất | Có thể tạo String đích lớn |
| `BITFIELD` | Đọc/ghi/tăng các trường bit có chiều rộng xác định | Phụ thuộc số thao tác | Khác bài toán một trạng thái boolean trên mỗi bit |

Các command này hoạt động trên byte của Redis String. Nếu key hiện là Hash, Set hoặc List, gọi `GETBIT` hay `SETBIT` sẽ gặp lỗi kiểu dữ liệu như `WRONGTYPE`.

### Đọc bit ngoài phạm vi đã cấp phát

```redis
GETBIT bitmap:never-created 123
# 0

BITCOUNT bitmap:never-created
# 0
```

Với key chưa tồn tại, `GETBIT` trả `0`. Điều này **không phân biệt**:

- Chưa từng có sự kiện.
- Có key nhưng bit chưa được bật.
- Key đã hết TTL hoặc bị xóa.
- Dữ liệu đã bị làm mới sang kỳ khác.

Nếu cần phân biệt trạng thái **“chưa biết”** với **“biết chắc là false”**, không thể chỉ dựa vào một bit; cần metadata, sự kiện hoặc nguồn dữ liệu tin cậy riêng.

### Đếm theo đoạn: `BITCOUNT` mặc định dùng byte offset

```redis
SETBIT demo:range 0 1
SETBIT demo:range 7 1
SETBIT demo:range 8 1

BITCOUNT demo:range
# 3

BITCOUNT demo:range 0 0
# 2: chỉ đếm byte đầu, gồm các bit offset 0..7

BITCOUNT demo:range 1 1
# 1: chỉ đếm byte thứ hai, gồm các bit offset 8..15
```

Ở các phiên bản Redis hỗ trợ tùy chọn đơn vị `BIT`, có thể chỉ định range theo **bit**, nhưng không nên mặc định mọi Redis server/client đều có cú pháp đó. Với `BITCOUNT key start end` thông thường, `start` và `end` **không phải hai bit offset**. Nhầm lẫn đơn vị sẽ dẫn tới kết quả sai.

`BITCOUNT` hỗ trợ các range theo quy tắc của Redis và xử lý phạm vi cuối **bao gồm end**. Nếu cần tính một nhóm bit không khớp ranh giới byte, phải áp dụng cách đọc/mask phù hợp hoặc dùng biến thể command có đơn vị bit khi server hỗ trợ.

## 4. Chọn bài toán phù hợp với Bitmap

Bitmap đặc biệt phù hợp với câu hỏi **đúng/sai trên miền ID đã được ánh xạ thành offset**:

- Người dùng ID 137 đã đăng nhập trong ngày hôm nay chưa?
- Tài khoản nào đã nhận một chiến dịch thông báo?
- Task có mã số nội bộ 8.012 đã được xử lý trong một lần chạy chưa?
- Những phiên kiểm thử nào đã hoàn tất?
- Đếm số người dùng hoạt động trên một ngày (nếu mỗi user ánh xạ duy nhất tới một bit).

Ví dụ mô hình đánh dấu đăng nhập mỗi ngày:

```text
Key: bitmap:login:2026-11-12

Offset 0  → userIndex 0 (tài khoản A)
Offset 1  → userIndex 1 (tài khoản B)
Offset 2  → userIndex 2 (tài khoản C)
...
Offset 99 → userIndex 99

User A đăng nhập → SETBIT key 0 1
User C đăng nhập → SETBIT key 2 1
Đếm user đã đăng nhập → BITCOUNT key = 2
```

Khác với Redis Set, bitmap **không tự giữ member ID**. Nếu cần liệt kê người dùng đã đăng nhập, phải biết cách chuyển từ offset về user ID. Nếu mapping bị mất hoặc ID được tái sử dụng, dữ liệu bitmap có thể trở nên không thể diễn giải đúng.

### Khi nào không nên dùng Bitmap?

| Yêu cầu | Vì sao Bitmap có thể không phù hợp | Lựa chọn cân nhắc |
| --- | --- | --- |
| ID là UUID ngẫu nhiên/string tự do | Không có offset số nhỏ, liên tục; ánh xạ ID → offset cần lưu riêng | Redis Set lưu member trực tiếp |
| Có vài trăm member trong không gian ID cực lớn | String phải dài tới offset cao nhất, rất tốn bộ nhớ | Redis Set; cấu trúc sparse khác |
| Cần lấy danh sách user theo thứ tự tham gia | Bitmap chỉ biểu diễn cờ, không lưu thứ tự/timestamp | Sorted Set hoặc database có index |
| Cần dữ liệu riêng của từng member | Mỗi bit chỉ có hai trạng thái | Hash hoặc key dữ liệu riêng |
| Cần TTL riêng cho mỗi member | Redis TTL cơ bản gắn với toàn key | Sorted Set score là deadline, hoặc key per member |
| Cần xóa và tái sử dụng ID thường xuyên | Bit cũ có thể bị hiểu là đối tượng mới | ID không tái sử dụng hoặc cơ chế generation/migration |
| Cần lưu số lần hành động của từng user | Bit chỉ nói đã/ chưa; không biểu thị số đếm | Counter, Hash hoặc cấu trúc phù hợp |

**Bitmap không phải Bloom filter.** Bitmap đánh dấu chính xác vị trí đã quy ước: nếu mapping không trùng và key không bị thay đổi ngoài dự kiến, không có false positive do thuật toán xác suất. Bloom filter sử dụng nhiều hàm băm/vị trí để tiết kiệm bộ nhớ trên tập dữ liệu lớn, chấp nhận xác suất false positive; đây là cấu trúc khác.

## 5. Thiết kế ánh xạ ID sang bit offset

Đây là bước quan trọng nhất trước khi code. `SETBIT` yêu cầu `offset` là số nguyên không âm, trong khi nghiệp vụ có thể dùng `UUID`, username, số hồ sơ hoặc ID từ database.

### 5.1. ID số dày đặc

Nếu mỗi user đã có **ID nguyên dương liên tục bắt đầu từ 1** và không bị tái sử dụng, có thể quy định:

\\[
\\text{offset} = \\text{userId} - 1
\\]

Ví dụ `userId=1` → offset `0`, `userId=10` → offset `9`. Cần kiểm tra `userId > 0` và giới hạn cho phép trước khi gửi sang Redis.

Trường hợp ID bắt đầu từ `0` thì offset có thể bằng chính ID. Quan trọng nhất là hợp đồng **nhất quán với mọi producer và consumer**.

### 5.2. ID số thưa hoặc UUID

Giả sử hiện chỉ có 100.000 user, nhưng ID lớn nhất là `900.000.000` vì hệ thống dùng snowflake-like ID hoặc cấp phát phân tán. Dùng trực tiếp ID làm offset có thể tạo chuỗi rất lớn, dù mới bật vài bit.

Có thể xây ánh xạ ổn định:

```text
user_uuid                           → denseIndex
7b...c1                             → 0
41...5d                             → 1
e2...99                             → 2
...
```

**Dense index** cần có nguồn quản lý bền vững, không trùng, không tái sử dụng tùy tiện, và có cơ chế đối soát trong nhiều instance. Redis bitmap không giải quyết việc cấp phát dense index cho bạn. Nếu phải duy trì một bảng mapping lớn chỉ để dùng bitmap, cần tính tổng chi phí của cả mapping và bitmap; đôi khi Redis Set đơn giản và tiết kiệm hơn ở quy mô thực.

### 5.3. Đừng dùng hash modulo tùy tiện để thay mapping

Một cách sai thường gặp:

```java
long offset = Math.abs(userId.hashCode()) % 1_000_000;
```

Hai user khác nhau có thể có cùng offset do **hash collision**. Khi user A bật bit, truy vấn user B cũng có thể thấy `1` dù B chưa đăng nhập. Phép modulo không tạo ra ánh xạ duy nhất; nếu ứng dụng chấp nhận xác suất sai thì đó đã là một bài toán cấu trúc xác suất khác, không phải bitmap membership chính xác.

Ngoài ra, `Math.abs(Integer.MIN_VALUE)` vẫn là số âm; do đó ví dụ trên còn có rủi ro kỹ thuật ngoài collision. Với bài toán cần độ chính xác, hãy dùng offset có tính duy nhất đã được bảo đảm.

### 5.4. Kiểm soát offset lớn

Redis áp dụng giới hạn cho offset của `GETBIT`/`SETBIT` theo kích thước String và giao thức. Trong những dòng Redis phổ biến, bitmap dựa trên giới hạn String tối đa khoảng **512 MiB**, tương ứng offset tối đa `2^32−1` bit, nhưng giới hạn thực tế và cấu hình có thể thay đổi theo phiên bản/server. Không dùng một giá trị cực lớn chỉ vì kiểu dữ liệu Java `long` cho phép.

Ngay cả offset **hợp lệ** có thể gây nguy hiểm: đặt bit ở vị trí rất cao trên một key mới buộc Redis cấp phát/zero-fill vùng byte tới đó, có thể gây gián đoạn và tăng bộ nhớ mạnh. Ứng dụng nên có giới hạn offset theo quy mô nghiệp vụ (ví dụ chỉ hỗ trợ denseIndex trong một miền đã cấp phát) thấp hơn nhiều so với giới hạn kỹ thuật tối đa của Redis.

## 6. Tạo project Spring Boot với Spring Data Redis

Trong ứng dụng Spring Boot, cần starter Redis:

**Gradle Groovy DSL**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

**Maven**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Khi project đã dùng Spring Boot parent hoặc BOM tương thích, starter thường không cần ghi version riêng. Ví dụ cấu hình kết nối dành cho Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Lettuce thường là Redis client được starter cung cấp theo mặc định. Trên Docker/Kubernetes, `localhost` trỏ tới network namespace của process ứng dụng; cần đổi thành hostname/service Redis thực tế.

### Vì sao chọn `StringRedisTemplate`?

`StringRedisTemplate` sử dụng serializer kiểu String/UTF-8 cho key và value, phù hợp với tên key đọc được bằng Redis CLI. Khi gọi `setBit`, Redis làm việc trực tiếp trên bytes của Redis String lưu dưới key đó; bạn không phải serialize một đối tượng Java thành “bitset binary” riêng.

Nên dành **namespace key riêng** cho bitmap, chẳng hạn `bitmap:login:YYYY-MM-DD`. Không dùng lẫn cùng một key cho JSON, text hay các giá trị String thông thường: `SETBIT` thay đổi byte cụ thể trong String và có thể làm hỏng payload text/JSON.

## 7. Spring Data Redis: đặt bit bằng `ValueOperations.setBit`

Phương thức:

```java
Boolean oldBit = stringRedisTemplate.opsForValue()
        .setBit("bitmap:login:2026-11-12", 137L, true);
```

Trong lời gọi thông thường, `setBit(key, offset, true)` gửi thao tác tương ứng với `SETBIT key offset 1`. Kết quả `Boolean` phản ánh **giá trị bit cũ**, không phải số lượng bit đang bật.

Để **xóa cờ** ở một vị trí:

```java
Boolean oldBit = stringRedisTemplate.opsForValue()
        .setBit("bitmap:login:2026-11-12", 137L, false);
```

Ứng dụng cần biết việc “xóa” này có hợp lệ về mặt nghiệp vụ hay không. Với dữ liệu kiểu “user đã từng đăng nhập trong ngày”, khi đã bật, thường **không xóa** khi người dùng đăng xuất. Với trạng thái hiện tại “online/offline”, việc xóa bit có thể cần thiết nhưng phải xử lý sự kiện mất kết nối và nhiều session đồng thời.

### Service ghi hoạt động trong ngày

Ví dụ service sau dùng dense index có giới hạn để đánh dấu một tài khoản hoạt động trong ngày. Giá trị index ở đây được cung cấp bởi một nguồn quản lý ID riêng của ứng dụng:

```java
import java.time.LocalDate;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DailyActivityBitmapService {

    // Mốc ví dụ mang tính chính sách của hệ thống, không phải giới hạn Redis.
    private static final long MAX_DENSE_INDEX = 9_999_999L;

    private final StringRedisTemplate redis;

    public DailyActivityBitmapService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean markActive(LocalDate day, long denseIndex) {
        validateIndex(denseIndex);
        String key = keyFor(day);

        Boolean wasActive = redis.opsForValue().setBit(
                key,
                denseIndex,
                true
        );

        // true: bit từ 0 chuyển sang 1 ở lần gọi này.
        // false: bit đã bật sẵn trước đó.
        if (wasActive == null) {
            throw new IllegalStateException("SETBIT returned no result");
        }
        return !wasActive;
    }

    public boolean wasActive(LocalDate day, long denseIndex) {
        validateIndex(denseIndex);
        Boolean active = redis.opsForValue().getBit(
                keyFor(day),
                denseIndex
        );

        if (active == null) {
            throw new IllegalStateException("GETBIT returned no result");
        }
        return active;
    }

    private static String keyFor(LocalDate day) {
        Objects.requireNonNull(day, "day");
        return "bitmap:login:" + day;
    }

    private static void validateIndex(long denseIndex) {
        if (denseIndex < 0 || denseIndex > MAX_DENSE_INDEX) {
            throw new IllegalArgumentException("Invalid denseIndex");
        }
    }
}
```

**Ngữ nghĩa của `markActive`:** trả `true` khi bit cũ là `0` và lệnh vừa đặt nó thành `1`; trả `false` nếu trước đó đã là `1`. Trong logic nghiệp vụ “lần đầu user hoạt động hôm nay”, kết quả có thể hữu ích, nhưng cần nhớ dữ liệu có thể bị mất do TTL, failover hoặc reset key; không dùng kết quả này thay cho chứng từ nghiệp vụ có yêu cầu bền vững tuyệt đối.

Trong pipelining/transaction, một số API Spring Data Redis có thể trả `null` vì kết quả được thu sau. Ví dụ này chủ ý dành cho lời gọi trực tiếp; nếu chuyển vào pipeline, cần xử lý response theo hợp đồng API tương ứng.

### Vì sao offset phải được validate?

Nếu consumer nhận một denseIndex tùy ý từ URL/request và chuyển thẳng vào `setBit`, người gọi có thể yêu cầu offset rất lớn, làm Redis cấp phát nhiều byte hoặc trả lỗi. Kiểm soát offset ở service giúp ràng buộc kích thước theo nghiệp vụ; ngoài ra endpoint vẫn cần xác thực/quyền thao tác để không cho user tự bật bit của người khác.

## 8. Spring Data Redis: đọc bit bằng `ValueOperations.getBit`

Đọc trạng thái của một user:

```java
Boolean active = stringRedisTemplate.opsForValue().getBit(
        "bitmap:login:2026-11-12",
        137L
);
```

`GETBIT` là thao tác nhỏ, phù hợp khi cần biết **một** user có bật cờ hay chưa. Không cần tải toàn bộ bitmap về Java bằng `GET`, cũng không cần gọi `BITCOUNT` nếu chỉ muốn kiểm tra một người.

### Phân biệt kết quả bit `0` và key không tồn tại

```redis
GETBIT bitmap:login:unknown-date 137
# 0

EXISTS bitmap:login:unknown-date
# 0
```

`GETBIT` trả 0 cho key không tồn tại, nhưng một key đã tồn tại có bit `137` bằng 0 cũng trả 0. Nếu API cần thông báo “dữ liệu ngày này chưa được tính” thay vì “không hoạt động”, hãy giữ metadata về thời điểm dữ liệu được bắt đầu/kết thúc hoặc trạng thái hoàn tất của job.

Gọi `EXISTS` rồi `GETBIT` bằng hai command **không tạo snapshot nhất quán** khi key có thể bị xóa/hết hạn giữa chừng. Nếu cần kết luận nguyên tử từ cả hai điều kiện, có thể dùng Lua/Redis Functions trong một key hoặc thiết kế trạng thái kiểm chứng ngoài bitmap.

## 9. Đếm bit bật bằng `BITCOUNT`

`BITCOUNT` trả số lượng bit có giá trị `1` trên một Redis String. Trong bài toán đánh dấu hoạt động, nếu **một user có đúng một offset và chỉ bật tối đa một lần mỗi ngày**, kết quả có thể đại diện cho số người dùng duy nhất đã hoạt động trong ngày đó.

```redis
SETBIT bitmap:login:2026-11-12 1 1
SETBIT bitmap:login:2026-11-12 3 1
SETBIT bitmap:login:2026-11-12 8 1
SETBIT bitmap:login:2026-11-12 3 1

BITCOUNT bitmap:login:2026-11-12
# 3, vì bit 3 chỉ được đếm một lần
```

Điều kiện để diễn giải con số này đúng:

- Mỗi user được ánh xạ tới **một offset riêng biệt**.
- Không có writer khác dùng cùng key cho một ý nghĩa khác.
- Bit được bật/giữ theo cùng chính sách nghiệp vụ.
- Key đại diện cho đúng ngày/kỳ cần đo (múi giờ, thời điểm cắt kỳ thống nhất).
- Không dùng tính năng tái sử dụng offset làm lẫn dữ liệu của hai tài khoản.

Nếu nhiều user cùng chung offset do lỗi mapping, `BITCOUNT` sẽ **đếm thiếu**. Nếu cùng user được cấp nhiều offset, hệ thống có thể **đếm thừa**. Redis không tự phát hiện các sai lệch đó.

### `BITCOUNT` có phải thao tác `O(1)`?

Không. Về bản chất, Redis cần đếm các bit bật trong những byte được xét. Chi phí thường được mô tả là **`O(N)` theo số byte của chuỗi** (hoặc số byte thuộc range). Khi bitmap dài hàng chục hoặc hàng trăm MB, việc gọi `BITCOUNT` liên tục trên request nóng có thể tạo tải CPU và ảnh hưởng độ trễ các command khác.

Ví dụ:

```text
Một triệu bit đã cấp phát       → khoảng 125 KB payload
Mười triệu bit đã cấp phát      → khoảng 1,25 MB payload
Một trăm triệu bit đã cấp phát  → khoảng 12,5 MB payload
```

Mỗi lần `BITCOUNT` toàn key đều có công việc tỉ lệ với số byte cần quét, dù chỉ có 100 bit bằng `1`. Cần quan sát tần suất đếm, chiều dài String và tải Redis trước khi quyết định dùng trong API đồng bộ có lưu lượng cao.

### 9.1. Gọi `BITCOUNT` bằng `RedisCallback`

Một cách đọc số bit bật trong Spring Data Redis là sử dụng API kết nối cấp thấp:

```java
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Objects;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DailyActivityCountService {

    private final StringRedisTemplate redis;

    public DailyActivityCountService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long countActive(LocalDate day) {
        Objects.requireNonNull(day, "day");
        String key = "bitmap:login:" + day;

        // StringRedisTemplate mặc định dùng UTF-8 cho tên key.
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);

        Long count = redis.execute(
                (RedisCallback<Long>) connection ->
                        connection.stringCommands().bitCount(keyBytes)
        );

        return Objects.requireNonNull(count, "BITCOUNT returned no result");
    }
}
```

`RedisCallback` cho phép dùng lệnh cấp thấp của Redis Connection. Cần sử dụng **chính encoding/key serializer** đã dùng khi ghi dữ liệu; ở ví dụ, key là UTF-8 từ `StringRedisTemplate`. Nếu ứng dụng tùy biến key serializer, không tự ý chuyển key bằng một encoding khác.

Các API Spring Data Redis có thể khác ít nhiều giữa các dòng phiên bản; mã trên mô tả cách sử dụng `RedisConnection.stringCommands().bitCount(byte[])` trong các phiên bản hỗ trợ interface này. Không cần tải toàn bộ raw bytes lên JVM rồi tự đếm nếu chỉ muốn số bit: Redis đã có lệnh `BITCOUNT`.

### 9.2. Khi cần count rất thường xuyên

Giả sử dashboard gọi `BITCOUNT` hàng trăm lần mỗi giây trên bitmap của toàn tháng. Nên cân nhắc:

1. **Cache số đếm** với TTL ngắn nếu nghiệp vụ chấp nhận độ trễ cập nhật.
2. **Tính định kỳ** bằng job ngoài luồng HTTP, lưu lại kết quả theo kỳ.
3. **Duy trì một counter cùng lúc bật bit** nếu cần cập nhật count nhanh, nhưng phải xử lý tính nguyên tử, failover và tái dựng khi counter lệch.
4. **Tách bitmap theo thời gian/phân vùng** nếu hoạt động đếm thường chỉ cần một đoạn dữ liệu nhỏ.

Một counter cập nhật theo `SETBIT` chỉ chính xác khi nó tăng **nếu bit cũ bằng 0**; tăng sau mọi lần gọi ghi sẽ đếm trùng user. Nếu `SETBIT` và `INCR` là hai command độc lập, ứng dụng có thể crash giữa chúng. Giải pháp nguyên tử là Lua/Redis Functions trong cùng một scope Redis có thể truy cập cả key bitmap và key counter theo quy tắc hash slot.

Với số đếm dùng cho báo cáo tài chính, thanh toán hoặc chỉ số cần khả năng tái lập, nên xác định nguồn dữ liệu chuẩn và quy trình đối soát thay vì dựa hoàn toàn vào một counter Redis.

## 10. Dùng Lua để đặt bit và tăng số đếm khi chuyển 0 → 1

Khi cần cả **bitmap** và **counter** cập nhật nhất quán trong một Redis node, có thể dùng script ngắn:

```lua
-- KEYS[1]: bitmap key
-- KEYS[2]: count key
-- ARGV[1]: bit offset

local oldBit = redis.call('SETBIT', KEYS[1], tonumber(ARGV[1]), 1)

if oldBit == 0 then
    redis.call('INCR', KEYS[2])
end

return oldBit
```

Lệnh `SETBIT` trả bit cũ. Nếu cũ là `0`, script tăng counter đúng một lần cho chuyển trạng thái thành `1`; nếu cũ là `1`, không tăng. Các lệnh trong script thực thi nguyên tử so với các command client khác trên node xử lý, giúp tránh race condition do nhiều request cùng đánh dấu một user.

### Chú ý về Redis Cluster

Script trên truy cập **hai key**. Trong Redis Cluster, các key được script truy cập phải nằm trong cùng hash slot theo giới hạn multi-key scripting. Ví dụ quy ước key chung một hash tag cho một ngày:

```text
bitmap:login:{2026-11-12}:data
bitmap:login:{2026-11-12}:count
```

Cả hai key có hash tag `{2026-11-12}` nên nằm cùng slot. Đổi lại, tất cả dữ liệu trong một ngày tập trung vào một slot; cần cân nhắc tải thực tế. Nếu hệ thống đã dùng key `bitmap:login:2026-11-12` không có hash tag, không thể tùy tiện thêm key count với slot khác rồi coi script sẽ hoạt động trong Cluster.

### Hạn chế của counter đi kèm

Nếu tác vụ khác xóa bitmap, đặt bit về 0, hoặc chỉ xóa riêng counter, hai trạng thái sẽ lệch. Nếu một ngày đã hết hạn nhưng counter còn sống, `count` không còn đại diện cho dữ liệu bitmap. Cần thiết kế **cùng vòng đời**, chính sách xóa, phân quyền writer và quy trình tái dựng count từ bitmap khi cần.

Tăng counter trong Lua không tạo ra durability mạnh hơn các cơ chế persistence/replication của Redis. Khi Redis gặp sự cố hoặc failover, tính bền vững vẫn phụ thuộc cấu hình hạ tầng. Đừng nhầm tính nguyên tử thực thi với tính bền vững qua mọi sự cố.

## 11. TTL cho bitmap theo ngày hoặc theo chiến dịch

Bitmap là Redis String nên TTL áp dụng **cho toàn bộ key**, không phải từng bit. Ví dụ:

```redis
SETBIT bitmap:login:2026-11-12 137 1
EXPIRE bitmap:login:2026-11-12 604800

TTL bitmap:login:2026-11-12
# Số giây còn lại, xấp xỉ tối đa 7 ngày
```

Đoạn này dùng hai command nên **không nguyên tử**. Nếu ứng dụng dừng ngay sau `SETBIT`, key có thể chưa được gắn TTL. Ngoài ra, nếu gọi `EXPIRE 604800` sau **mỗi** lần đánh dấu, deadline sẽ được gia hạn theo mỗi lượt ghi. Điều đó có thể trái với quy tắc lưu dữ liệu đúng bảy ngày kể từ khi tạo key hoặc đúng bảy ngày sau ngày thống kê.

### 11.1. Tạo bitmap và TTL cùng một script

Redis `SETBIT` không có tùy chọn `EX`/`PX` như `SET`. Nếu cần bảo đảm **lần tạo đầu tiên** có TTL, có thể dùng Lua:

```lua
-- KEYS[1]: bitmap key
-- ARGV[1]: offset
-- ARGV[2]: TTL seconds (positive)

local absent = redis.call('EXISTS', KEYS[1]) == 0
local oldBit = redis.call('SETBIT', KEYS[1], tonumber(ARGV[1]), 1)

if absent then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end

return oldBit
```

Nếu key chưa tồn tại, script sẽ vừa đặt bit vừa thiết lập TTL trước khi trả kết quả; không có command client khác xen giữa hai thao tác trong lúc script thực thi. Nếu key đã tồn tại, nó giữ nguyên hạn dùng cũ. Đây là một lựa chọn chính sách: “TTL được bắt đầu khi bitmap tạo lần đầu”, không phải “TTL từ hoạt động cuối cùng”.

**Giới hạn:** nếu key **đã tồn tại nhưng không có TTL** do dữ liệu cũ hoặc writer khác, script trên không tự sửa trạng thái đó. Một hệ thống mà mọi bitmap luôn phải hết hạn có thể bổ sung quy tắc kiểm tra `TTL == -1` trong script rồi đặt expiration, hoặc chạy job sửa dữ liệu cũ. Hãy phân biệt chính sách trước khi thêm điều kiện.

### 11.2. Hết hạn tại một deadline tuyệt đối

Với dữ liệu thống kê theo ngày, đôi khi muốn tất cả key ngày `D` hết hạn vào thời điểm cố định, ví dụ **00:00 UTC sau D + 30 ngày**, dù user đầu tiên hoạt động lúc nào. Khi đó việc đặt thời gian hết hạn bằng mốc Unix có thể phù hợp hơn `EXPIRE N` tính từ lúc ghi.

Nếu dùng `EXPIREAT`/`PEXPIREAT` trong script, phải xác định rõ:

- Múi giờ tạo ngày thống kê: UTC hay múi giờ nghiệp vụ.
- Deadline được tính bằng Unix seconds hay milliseconds.
- Key của ngày quá hạn có được phép tạo lại không.
- Nếu hệ thống có nhiều múi giờ, một sự kiện thuộc ngày nào tại thời điểm cắt kỳ.

Thao tác đặt bit vào key ngày đã quá hạn có thể tạo lại key nếu writer không kiểm tra kỳ hợp lệ. TTL chỉ dọn dữ liệu; nó không tự từ chối sự kiện tới trễ theo chính sách nghiệp vụ.

### 11.3. Trường hợp có nhiều session

Nếu bitmap thể hiện “đã từng đăng nhập hôm nay”, `SETBIT ... 1` có thể được gọi nhiều lần với cùng offset, không làm tăng `BITCOUNT`. Nhưng nếu bitmap biểu diễn “đang online”, việc đăng xuất của một session không đồng nghĩa user đã offline khi session thứ hai còn kết nối. Một bit/user **không đủ** để đếm số session đồng thời; cần cấu trúc hoặc cơ chế presence phù hợp.

## 12. Đếm người hoạt động nhiều ngày và thao tác `BITOP`

Một lợi ích của bitmap có cùng ánh xạ offset là có thể kết hợp các ngày bằng phép toán bit:

```text
Ngày A:     1 0 1 0 0 1 0 0
Ngày B:     0 1 1 0 0 0 1 0

OR:         1 1 1 0 0 1 1 0  → đã hoạt động ở ít nhất một ngày
AND:        0 0 1 0 0 0 0 0  → có hoạt động ở cả hai ngày
```

Redis CLI:

```redis
BITOP OR bitmap:union:temp bitmap:login:2026-11-11 bitmap:login:2026-11-12
BITCOUNT bitmap:union:temp

BITOP AND bitmap:intersection:temp bitmap:login:2026-11-11 bitmap:login:2026-11-12
BITCOUNT bitmap:intersection:temp
```

Diễn giải:

- `OR` đặt bit `1` nếu user hoạt động **ít nhất một** ngày.
- `AND` đặt bit `1` nếu user hoạt động **cả hai** ngày.
- `XOR` đặt bit `1` nếu bit khác nhau giữa hai dữ liệu đầu vào, phù hợp với bài toán đối xứng.

`BITOP` lưu kết quả vào một **Redis String đích**. Đây là dữ liệu phát sinh có thể chiếm bộ nhớ; cần có namespace và TTL/xóa rõ ràng. Không dùng key kết quả trùng với dữ liệu nguồn nếu nghiệp vụ không chủ ý ghi đè.

### Điều kiện để phép OR/AND có ý nghĩa

Các bitmap phải có **cùng ánh xạ offset → user**. Nếu ngày A dùng offset `42` cho user X còn ngày B dùng offset `42` cho user Y, phép OR/AND vẫn cho kết quả số học nhưng sai về người dùng. Việc tái sử dụng dense index theo thời gian sẽ phá hỏng phép đối chiếu liên kỳ.

Trong Redis Cluster, phép `BITOP` nhiều key phải tuân thủ quy tắc slot như các multi-key command khác. Không mặc định những key theo ngày khác nhau luôn cùng hash slot; nếu cần tính tổng hợp liên node, phải thay thiết kế key/hash tag hoặc tổng hợp theo một cơ chế khác.

### Chi phí của phép toán tập hợp bit

`BITOP` thường phải xét byte của các String đầu vào, với chi phí phụ thuộc chiều dài dữ liệu; nó không phải thao tác `O(1)` cho một tập một trăm triệu bit. Kết quả cũng được materialize thành String mới. Với dashboard truy vấn nhiều khoảng ngày, có thể cần batch job tạo snapshot tổng hợp theo tuần/tháng hoặc một công cụ analytics chuyên dụng thay vì chạy `BITOP` toàn bộ dữ liệu ở mỗi HTTP request.

## 13. Ước lượng bộ nhớ và tác động của offset thưa

Một bitmap dài tới offset cao nhất `M` có payload ít nhất:

\\[
\\text{bytes} = \\left\\lfloor \\frac{M}{8} \\right\\rfloor + 1
\\]

khi `M ≥ 0` đã được cấp phát. Công thức này cho **số byte của Redis String** cần có để giữ bit tại offset `M`; còn thực tế Redis sẽ có overhead object/allocator và các chi phí khác.

| Offset cao nhất được ghi | Số byte tối thiểu của String | Khoảng dung lượng |
| --- | ---: | --- |
| 7 | 1 | 1 B |
| 999 | 125 | 125 B |
| 999.999 | 125.000 | ~122 KiB |
| 9.999.999 | 1.250.000 | ~1,19 MiB |
| 99.999.999 | 12.500.000 | ~11,92 MiB |
| 999.999.999 | 125.000.000 | ~119,21 MiB |

Giả sử chỉ có 2.000 user hoạt động nhưng index lớn nhất là `999.999.999`, bitmap có thể dùng khoảng 125 MB payload do phải biểu diễn tới vị trí đó. Redis Set chứa 2.000 member trực tiếp có thể hiệu quả hơn rất nhiều, dù Set có overhead cho từng member.

**Quy tắc lựa chọn:** đừng đánh giá bitmap dựa vào số bit `1`, hãy nhìn **offset cao nhất có thể xuất hiện** và mật độ ID trong dải đó.

### Big key và latency

Một lệnh `SETBIT` vào offset cao trên String chưa tồn tại có thể yêu cầu cấp phát một khối bộ nhớ lớn và khởi tạo byte bằng 0. Ngay cả khi độ phức tạp thao tác ghi bit được mô tả gần `O(1)`, **lần mở rộng đầu tiên** vẫn có thể tạo chi phí cấp phát/zero-fill đáng kể và gây tăng latency.

Một `BITCOUNT` trên String nhiều MB có thể quét lượng byte lớn nhiều lần. Nếu Redis phục vụ các request khác trong cùng instance, những thao tác bitmap lớn có thể ảnh hưởng độ trễ chung. Cần kiểm soát input và kích thước trước khi tăng số replica ứng dụng hoặc tăng traffic của dashboard đếm.

## 14. Giám sát bitmap trên Redis và Spring Boot

Các lệnh Redis CLI có thể dùng để điều tra một key bitmap:

```redis
TYPE bitmap:login:2026-11-12
STRLEN bitmap:login:2026-11-12
BITCOUNT bitmap:login:2026-11-12
GETBIT bitmap:login:2026-11-12 137
TTL bitmap:login:2026-11-12
MEMORY USAGE bitmap:login:2026-11-12
```

| Lệnh | Điều có thể suy ra |
| --- | --- |
| `TYPE` | Bitmap phải xuất hiện như một Redis `string` |
| `STRLEN` | Số byte trong String; giúp suy ra offset đã được cấp phát |
| `BITCOUNT` | Số bit bật; phải hiểu đúng mapping và chi phí đếm |
| `GETBIT` | Trạng thái ở một offset đã biết |
| `TTL` | Vòng đời của cả key; `-1` là key không có TTL, `-2` là key không tồn tại |
| `MEMORY USAGE` | Dung lượng Redis phân bổ cho key; không đồng nhất tuyệt đối với `STRLEN` |

Quan sát bổ sung từ Redis và ứng dụng:

```redis
INFO commandstats
INFO memory
SLOWLOG GET 20
```

`SLOWLOG` tập trung vào thời gian thực thi lệnh trong Redis, không gồm toàn bộ latency mạng hoặc client. Ở Spring Boot, cần quan sát thêm thời gian gọi Redis, timeout, pool wait, lỗi serializer, throughput và số lần thực hiện `BITCOUNT`; không phải mọi chỉ số đều tự có nếu chưa cấu hình telemetry.

### Kịch bản cần đo tải

1. Nhiều worker cùng đặt bit `1` cho một user — `BITCOUNT` không được tăng trùng.
2. Hàng nghìn user khác nhau đánh dấu trong cùng ngày — kiểm tra throughput `SETBIT` và Redis CPU.
3. Lần đầu tạo bitmap tại offset cao — theo dõi độ trễ và memory spike.
4. Dashboard gọi `BITCOUNT` đồng thời với các request nóng khác — xem p95/p99.
5. Gần đến deadline TTL — kiểm tra logic không ghi lại key ngày cũ ngoài chính sách.
6. Khôi phục/restart Redis — xác định kỳ vọng về persistence và nguồn dữ liệu đối soát.

Chỉ kiểm tra `BITCOUNT` bằng một bitmap 64 bit trên máy phát triển chưa đại diện cho hiệu năng của bitmap 100 triệu bit trong production.

## 15. Các lỗi thường gặp và cách nhận diện

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| `GETBIT` luôn trả `0` | Key chưa tồn tại, sai offset, sai Redis database/prefix, key đã hết TTL | Kiểm tra key, mapping, `TTL` và kết nối |
| `BITCOUNT` thấp hơn số user thực | Nhiều user chung offset, key bị xóa hoặc tái tạo, một số event không ghi | Đối soát mapping và luồng ghi |
| `BITCOUNT` cao hơn số user thực | Một user có nhiều index, writer bật bit không hợp lệ, tái sử dụng ID sai | Kiểm tra quy tắc cấp phát index và dữ liệu nguồn |
| Lần `SETBIT` đầu rất chậm | Offset cao làm Redis phải cấp phát String lớn | Giới hạn offset và dùng dense index thực |
| Redis memory tăng đột ngột | Viết bit vào vị trí rất xa, tạo nhiều key bitmap theo kỳ không dọn | `STRLEN`, `MEMORY USAGE`, kiểm tra ID input và TTL |
| `BITCOUNT` chậm dù ít bit `1` | String rất dài, nhiều bit `0` vẫn phải xét | Xem `STRLEN`, giảm frequency hoặc phân đoạn |
| Dashboard đếm trùng sau khi thêm counter riêng | Mỗi lần `SETBIT` đều tăng counter, kể cả bit cũ `1` | Chỉ tăng trên chuyển `0 → 1`, cùng thao tác nguyên tử |
| `BITCOUNT key 0 0` cho kết quả lạ | Range mặc định theo **byte**, không theo bit | Phân biệt byte offset và bit offset |
| Lệnh báo `WRONGTYPE` | Key đang chứa Hash/Set/List thay vì String | Dùng namespace bitmap riêng, kiểm tra `TYPE` |
| Dữ liệu ngày trước bị mất bất ngờ | TTL hết hạn hoặc key bị xóa | Xác định chính sách retention và nguồn dữ liệu chuẩn |
| User offline nhưng bit vẫn bằng `1` | Bitmap là “đã từng online” chứ không phải trạng thái hiện tại | Xác định lại ý nghĩa bit và session/presence logic |
| Bit của user cũ “chuyển” sang user mới | Dense index được tái sử dụng | Không tái sử dụng index nếu dữ liệu cũ còn hiệu lực |

### Phân biệt lỗi kết nối và lỗi dữ liệu

Nếu Spring Data Redis báo `RedisConnectionFailureException` hoặc timeout ở bước kết nối, chưa thể kết luận bitmap sai. Cần kiểm tra Redis endpoint, xác thực, mạng và cấu hình client trước. Khi ứng dụng đọc được key, mới phân tích offset, serializer, kiểu Redis, TTL và số bit.

## 16. Bài thực hành theo bước

Các lệnh sau dành cho Redis thử nghiệm. Sử dụng namespace riêng và xóa các key tạo ra khi kết thúc nếu không cần giữ.

### Bài A — Đặt, đọc và đếm bit

```redis
DEL lesson:bitmap:a
SETBIT lesson:bitmap:a 2 1
SETBIT lesson:bitmap:a 5 1
SETBIT lesson:bitmap:a 2 1
GETBIT lesson:bitmap:a 2
GETBIT lesson:bitmap:a 3
BITCOUNT lesson:bitmap:a
STRLEN lesson:bitmap:a
```

Kỳ vọng: hai lệnh đầu `SETBIT` trả bit cũ bằng `0`; lần ghi lại offset `2` trả `1`. `GETBIT ... 2` là `1`, `GETBIT ... 3` là `0`, `BITCOUNT` là `2` và `STRLEN` là `1` byte.

### Bài B — Xóa bit

```redis
SETBIT lesson:bitmap:a 5 0
GETBIT lesson:bitmap:a 5
BITCOUNT lesson:bitmap:a
```

Kỳ vọng: lần đặt `0` ở bit đang bật trả giá trị cũ `1`, sau đó bit `5` bằng `0` và chỉ còn một bit `1` trong bitmap.

### Bài C — Xác nhận range mặc định theo byte

```redis
DEL lesson:bitmap:b
SETBIT lesson:bitmap:b 0 1
SETBIT lesson:bitmap:b 7 1
SETBIT lesson:bitmap:b 8 1
BITCOUNT lesson:bitmap:b 0 0
BITCOUNT lesson:bitmap:b 1 1
BITCOUNT lesson:bitmap:b
```

Kỳ vọng: lần lượt `2`, `1` và `3`. `0 0` chỉ byte đầu tiên, không phải chỉ bit offset `0`.

### Bài D — Khám phá chi phí của offset cao

Trên môi trường thử nghiệm được phép, hãy thử một dải offset vừa phải và quan sát:

```redis
DEL lesson:bitmap:capacity
SETBIT lesson:bitmap:capacity 999999 1
STRLEN lesson:bitmap:capacity
BITCOUNT lesson:bitmap:capacity
MEMORY USAGE lesson:bitmap:capacity
```

Kỳ vọng: `STRLEN` bằng `125000` byte, nhưng `BITCOUNT` chỉ bằng `1`. Mức `MEMORY USAGE` thường lớn hơn raw payload do overhead. Không cần tăng offset lên mức hàng trăm triệu để hiểu cơ chế; làm như vậy trên Redis dùng chung có thể gây ảnh hưởng tài nguyên.

### Bài E — Bài toán nghiệp vụ

Giả sử công ty có 1 triệu ID user **dày đặc từ 1 đến 1.000.000**, muốn đếm người đã truy cập ứng dụng trong ngày, không cần thứ tự. Hãy:

1. Định nghĩa `offset = userId - 1`.
2. Đặt key `bitmap:login:<ngày-UTC>`.
3. Dùng `SETBIT key offset 1` khi user truy cập.
4. Dùng `GETBIT` để kiểm tra một user.
5. Dùng `BITCOUNT` khi cần thống kê tổng số user khác nhau trong ngày.
6. Quy định retention, tránh gia hạn TTL không chủ ý sau mỗi lượt truy cập.

Sau đó thay đổi giả định: các ID hiện có là UUID ngẫu nhiên và chỉ có 10.000 user hoạt động. Hãy so sánh tổng chi phí của ánh xạ UUID → dense offset với phương án Redis Set lưu trực tiếp UUID. Không có một lựa chọn luôn tối ưu; quyết định theo cardinality, memory, truy vấn và chi phí quản lý mapping.

## 17. Câu hỏi tự luyện

**Câu 1.** Redis `TYPE bitmap:login:2026-11-12` trả kết quả gì sau khi đã tạo bitmap bằng `SETBIT`? Vì sao?

*Gợi ý:* Redis lưu Bitmap dưới dạng String, không phải một kiểu `bitmap` độc lập.

**Câu 2.** `SETBIT k 10 1` trả `0`. Có nghĩa là tổng số bit `1` hiện bằng `0` không?

*Gợi ý:* Giá trị trả về của `SETBIT` là **bit cũ tại offset**.

**Câu 3.** Tập user ID có giá trị lớn nhất 100 triệu, nhưng chỉ vài trăm ID hiện hữu. Dùng ID trực tiếp làm bit offset có lợi không?

*Gợi ý:* Dung lượng String dựa trên offset cao nhất, không dựa trên số bit bật.

**Câu 4.** `GETBIT k 99` trả 0. Có thể suy ra “user 99 chắc chắn chưa từng hoạt động” không?

*Gợi ý:* Key có thể chưa tồn tại, đã hết TTL hoặc offset mapping đã thay đổi.

**Câu 5.** Vì sao `BITCOUNT` không nên được xem như một counter `O(1)` khi bitmap rất dài?

*Gợi ý:* Redis cần xét byte trong phạm vi đếm.

**Câu 6.** `BITCOUNT k 0 0` có đếm chính xác một bit tại offset `0` hay không?

*Gợi ý:* Theo cú pháp mặc định, start/end là byte offset.

**Câu 7.** Ứng dụng giữ bitmap cho từng ngày và cần biết user nào hoạt động **ít nhất một trong hai ngày**. Khi nào `BITOP OR` có ý nghĩa chính xác?

*Gợi ý:* Offset của một user phải giữ cùng ý nghĩa ở cả hai ngày, kết quả cần quản lý key/TTL riêng.

**Câu 8.** Hai request đồng thời đánh dấu user 10.000 bằng `SETBIT`. Tại sao cả hai không tạo hai bit bật?

*Gợi ý:* Mỗi offset chỉ chứa một bit, lệnh `SETBIT` thao tác nguyên tử trên vị trí đó.

**Câu 9.** Muốn giữ counter số user hoạt động tăng ngay khi một bit được bật lần đầu. Vì sao gọi `SETBIT` rồi `INCR` không đủ cho độ chính xác trong trường hợp crash?

*Gợi ý:* Hai command riêng có thể chỉ thực hiện một phần; script giúp gộp khi thỏa điều kiện Redis key/slot.

**Câu 10.** User có ba session cùng hoạt động. Nếu mỗi bit ứng với một user, `BITCOUNT` thể hiện số user hay số session?

*Gợi ý:* Ý nghĩa của bit phụ thuộc cách ánh xạ định danh.

## 18. Ghi nhớ

**Redis Bitmap là Redis String được thao tác theo bit.** Với `SETBIT`, ứng dụng đặt trạng thái `0/1` tại một offset; `GETBIT` kiểm tra một offset; `BITCOUNT` đếm tất cả bit được bật. Trong Spring Data Redis, `StringRedisTemplate.opsForValue().setBit/getBit` là cách trực tiếp để làm việc với một bit; có thể dùng `RedisCallback` với `RedisConnection.stringCommands().bitCount(...)` khi cần đếm.

Bitmap rất gọn khi **mỗi đối tượng có offset ổn định và không gian ID dày đặc**. Nhưng `BITCOUNT` tốn chi phí theo chiều dài byte, `SETBIT` ở offset rất cao có thể cấp phát String lớn, và một bit không chứa timestamp, thông tin thành viên hay TTL riêng. Thiết kế phù hợp phải xác định trước **offset mapping, namespace key, ngày/kỳ thống kê, chính sách retention, giới hạn kích thước và yêu cầu đồng thời**. Nếu cần ID tùy ý, danh sách thành viên hoặc phân trang, Redis Set/Sorted Set có thể phù hợp hơn; nếu cần số liệu bền vững, hãy giữ nguồn dữ liệu và cơ chế đối soát độc lập với bitmap.
