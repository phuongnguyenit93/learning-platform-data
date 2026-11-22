# HyperLogLog và phép ước lượng số phần tử phân biệt

Trong một hệ thống Spring Boot có lượng truy cập lớn, câu hỏi **“hôm nay có bao nhiêu người truy cập khác nhau?”** thường quan trọng hơn câu hỏi **“đã nhận bao nhiêu lượt truy cập?”**. Một người có thể mở cùng trang mười lần, nhưng vẫn chỉ được tính là **một người truy cập phân biệt** trong khoảng thời gian đó.

Redis cung cấp **HyperLogLog (HLL)** để **ước lượng cardinality** — số lượng giá trị phân biệt — với bộ nhớ nhỏ và gần như cố định. Spring Data Redis cho phép sử dụng tính năng này qua `HyperLogLogOperations` và các phương thức như `add()`, `size()`, `union()` và `delete()`.

Đổi lại, HyperLogLog **không lưu danh sách đầy đủ các phần tử** và **không cho kết quả chính xác tuyệt đối**. Nó phù hợp với các thống kê gần đúng trên tập rất lớn, nhưng không phù hợp với bài toán phải biết chính xác từng user hay thực hiện đối soát tài chính.

## 1. Phân biệt số lượt và số phần tử phân biệt

Giả sử hệ thống nhận chuỗi sự kiện:

~~~text
09:00  user-A xem trang sản phẩm
09:01  user-B xem trang sản phẩm
09:02  user-A xem lại trang sản phẩm
09:03  user-C xem trang sản phẩm
09:04  user-A xem thêm lần nữa
09:05  user-B xem lại trang
~~~

Có hai thước đo khác nhau:

| Thước đo | Kết quả trong ví dụ | Ý nghĩa |
|---|---:|---|
| Tổng lượt xem (page views) | **6** | Mỗi sự kiện được tính một lần |
| Số người xem phân biệt (unique viewers) | **3** | user-A, user-B, user-C, mỗi người một lần |

Nếu chỉ cần **tổng sự kiện**, một bộ đếm Redis như `INCR pageviews:2026-11-12` là đủ:

~~~bash
INCR pageviews:2026-11-12
~~~

Nhưng `INCR` **không biết** sự kiện đến từ user đã từng xuất hiện hay chưa. Muốn đếm số giá trị phân biệt, ta có các hướng:

1. **Redis Set**: thêm từng định danh bằng `SADD` và lấy số lượng chính xác bằng `SCARD`.
2. **HyperLogLog**: đưa từng định danh vào cấu trúc thống kê bằng `PFADD` và lấy **ước lượng** bằng `PFCOUNT`.
3. **Database/analytics engine**: thực hiện truy vấn đếm phân biệt, có thể chính xác hoặc gần đúng tùy hệ thống và nhu cầu lưu trữ.

Điểm quyết định là **có cần biết từng phần tử thuộc tập không**, hay chỉ cần một con số xấp xỉ.

## 2. HyperLogLog là gì?

**HyperLogLog** là cấu trúc dữ liệu xác suất (probabilistic data structure) dùng để ước lượng **cardinality** của tập giá trị đã quan sát. Nó được thiết kế để không phải giữ lại từng phần tử đã thêm vào.

Hình dung ba luồng dữ liệu:

~~~text
Các visitor ID:

  user-A, user-B, user-A, user-C, user-B, user-D, ...
      |       |       |       |       |
      +-------+-------+-------+-------+
                          |
                          v
                    Redis HyperLogLog
                    key: uv:2026-11-12
                          |
                    PFCOUNT key
                          |
                          v
                Ước lượng khoảng 4
             (không trả lại danh sách ID)
~~~

Thay vì lưu `user-A`, `user-B`, `user-C` trong một tập có thể liệt kê, HLL tính các đặc trưng thống kê từ **giá trị băm** của phần tử và duy trì một tập nhỏ các **register**. Khi có giá trị mới, các register có thể thay đổi; thuật toán dùng trạng thái register để suy ra số phần tử phân biệt đã quan sát.

Đây là mô tả trực giác, không phải yêu cầu bạn phải tự triển khai thuật toán. **Redis Server** xử lý các chi tiết HLL; ứng dụng Spring Data Redis gửi lệnh và nhận kết quả qua driver.

### 2.1. Đặc tính cốt lõi

| Đặc tính | HyperLogLog trong Redis |
|---|---|
| Mục đích | Ước lượng số giá trị phân biệt |
| Lưu đầy đủ từng phần tử? | **Không** |
| Có thể hỏi “user-A đã từng có trong tập chưa”? | **Không** |
| Có thể liệt kê tất cả ID đã thêm? | **Không** |
| Có thể thêm lại phần tử đã thấy? | **Có**, nhưng không làm thay đổi tập phân biệt về mặt ý nghĩa |
| Có thể xóa riêng một phần tử? | **Không** theo API HLL thông thường |
| Có thể xóa toàn bộ HLL key? | **Có**, như các Redis key khác |
| Có thể hợp nhất nhiều HLL? | **Có**, `PFMERGE` hoặc `PFCOUNT` nhiều key |
| Độ chính xác | **Gần đúng**, sai số thống kê |
| Bộ nhớ | Nhỏ, giới hạn gần mức **12 KiB** cho biểu diễn dense điển hình, chưa tính overhead key/metadata |

### 2.2. Tại sao bộ nhớ của HLL nhỏ?

Với Redis HyperLogLog chuẩn, cấu trúc dense sử dụng các register để lưu thông tin thống kê. Mức bộ nhớ thường được nhắc đến là **khoảng 12 KiB** cho trạng thái HLL dense của một key, không tăng tuyến tính theo số user duy nhất như Redis Set.

Redis cũng có biểu diễn **sparse** tiết kiệm hơn khi cardinality còn nhỏ; khi số lượng và phân bố dữ liệu tăng, HLL có thể chuyển sang dạng dense. Mức 12 KiB là **kích thước biểu diễn đặc trưng**, không có nghĩa toàn bộ chi phí của Redis key bằng chính xác 12.288 bytes: còn tên key, metadata, quản lý bộ nhớ, TTL và chi phí nội bộ.

Ví dụ về tăng trưởng:

~~~text
Redis Set:
  100 ID -> lưu dữ liệu từng ID
  1 triệu ID -> tiếp tục lưu từng ID, bộ nhớ tăng theo số phần tử

Redis HyperLogLog:
  100 ID -> cấu trúc thống kê nhỏ
  1 triệu ID -> cấu trúc thống kê gần cùng mức trần bộ nhớ
~~~

Khi chỉ cần **số lượng người truy cập gần đúng**, lợi thế bộ nhớ có thể rất lớn. Tuy nhiên, đổi lấy lợi thế đó là không thể truy xuất lại phần tử cụ thể và không có số đếm chính xác tuyệt đối.

## 3. Độ chính xác: hiểu đúng sai số khoảng 0,81%

Redis HyperLogLog thường được mô tả có **standard error khoảng 0,81%**. Đây là **đặc trưng thống kê** của thuật toán, không phải lời cam kết rằng mọi kết quả đều nằm trong phạm vi ±0,81% của giá trị thật.

Ví dụ nếu số người truy cập thực tế là **1.000.000**, giá trị `PFCOUNT` có thể gần một triệu nhưng không nhất thiết đúng bằng một triệu. Mức 0,81% tương ứng với độ lớn khoảng:

~~~text
1.000.000 × 0,0081 = 8.100
~~~

Con số **8.100** diễn giải quy mô sai số chuẩn trong ví dụ, **không phải giới hạn sai số tuyệt đối**. Một lần ước lượng có thể sai ít hơn hoặc nhiều hơn; cần hiểu bản chất xác suất thay vì xem kết quả là số kiểm toán.

Một vài hệ quả:

- Số đếm `PFCOUNT` là **ước lượng**, không được đưa vào điều kiện nghiệp vụ yêu cầu đúng chính xác từng user.
- Khi cardinality thấp, kết quả có thể thường trùng số thật nhờ cơ chế ước lượng phù hợp, nhưng **không nên viết hệ thống dựa trên giả định luôn chính xác**.
- Khi cardinality lớn, mức sai số tương đối nhỏ thường có ích cho dashboard thống kê và so sánh xu hướng.
- Không dùng HLL làm nguồn duy nhất cho thanh toán theo số user duy nhất nếu hợp đồng đòi hỏi số chính xác.

### 3.1. “Không chính xác” không có nghĩa “không đáng dùng”

Giả sử dashboard cần biết khoảng **2,5 triệu** hay **2,6 triệu** người dùng truy cập trong tuần. Việc giữ một sketch ước lượng có thể hợp lý hơn lưu hàng triệu định danh trong Redis chỉ để đếm, nếu sai số thống kê được chấp nhận.

Ngược lại, nếu hệ thống phải chứng minh chỉ có **100 suất đăng ký** và chặn người thứ 101, HyperLogLog hoàn toàn không phải cấu trúc phù hợp để thực thi giới hạn đó.

**Nguyên tắc:** yêu cầu mức chính xác được quyết định bởi nghiệp vụ, không phải bởi việc một API Redis có hiệu năng tốt.

## 4. Ba lệnh Redis quan trọng: PFADD, PFCOUNT, PFMERGE

Redis cung cấp giao diện HyperLogLog bằng các lệnh có tiền tố **PF**:

~~~text
PFADD  key element [element ...]
PFCOUNT key [key ...]
PFMERGE destination source [source ...]
~~~

Lưu ý: đây là **tên lệnh thực tế của Redis**; chúng không phải `SADD`, `SCARD` hoặc `SUNION` của Redis Set.

### 4.1. PFADD: thêm giá trị vào cấu trúc thống kê

Ví dụ:

~~~bash
PFADD demo:hll:visitors user-A user-B user-C
PFADD demo:hll:visitors user-A
PFADD demo:hll:visitors user-D
~~~

Ý nghĩa:

- Mỗi phần tử được chuyển thành thông tin thống kê trong HLL.
- Thêm lại `user-A` không làm user-A trở thành hai người phân biệt.
- Redis không giữ một danh sách đầy đủ để ta đọc lại bằng lệnh dành cho Set.

#### Giá trị trả về của PFADD rất dễ bị hiểu nhầm

Redis `PFADD` trả về:

- **1** nếu ít nhất một register của HLL được thay đổi.
- **0** nếu không register nào thay đổi.

**Không được dùng giá trị trả về 1 như bằng chứng chắc chắn “đây là user mới”, hoặc 0 như bằng chứng chắc chắn “user đã tồn tại”.** Một giá trị phân biệt chưa từng xuất hiện có thể không làm register thay đổi vì trạng thái HLL đã ghi nhận mức thống kê bằng hoặc lớn hơn.

Nói cách khác:

~~~text
PFADD trả 1  ≠ chắc chắn số người phân biệt tăng đúng 1
PFADD trả 0  ≠ chắc chắn phần tử đã từng được thêm trước đây
~~~

Trong Spring Data Redis, `HyperLogLogOperations.add(...)` cũng trả về một giá trị biểu thị kết quả lệnh, **không phải phương thức kiểm tra membership**.

### 4.2. PFCOUNT: lấy số lượng phân biệt ước lượng

~~~bash
PFCOUNT demo:hll:visitors
~~~

Redis trả về một số nguyên biểu thị **ước lượng cardinality** của HLL, ví dụ gần số phần tử phân biệt đã thêm.

Nếu key chưa tồn tại, trường hợp thông thường `PFCOUNT` cho kết quả **0** mà không cần khởi tạo HLL trước. Nếu key tồn tại nhưng dữ liệu không phải định dạng HLL hợp lệ, thao tác có thể báo lỗi.

### 4.3. PFCOUNT với nhiều key: ước lượng hợp của các tập

~~~bash
PFCOUNT uv:2026-11-11 uv:2026-11-12
~~~

Kết quả thể hiện **ước lượng số phần tử phân biệt trong hợp của hai HLL**, không phải tổng hai số `PFCOUNT` riêng lẻ.

Ví dụ:

~~~text
Ngày 11:
  A, B, C    -> 3 người

Ngày 12:
  B, C, D    -> 3 người

Tổng lượt người theo ngày: 3 + 3 = 6
Người phân biệt trong cả 2 ngày: A, B, C, D = 4
~~~

Vì B và C xuất hiện ở cả hai ngày, **ước lượng hợp** mới là thước đo hợp lý cho “unique users trong hai ngày”. Cộng số `PFCOUNT` từng ngày sẽ **đếm trùng người quay lại**.

### 4.4. PFMERGE: lưu hợp nhiều HLL vào một key đích

~~~bash
PFMERGE uv:two-days uv:2026-11-11 uv:2026-11-12
PFCOUNT uv:two-days
~~~

`PFMERGE` hợp nhất thông tin thống kê của các HLL nguồn và lưu vào **destination key**. Ta có thể dùng kết quả cho báo cáo theo tuần/tháng hoặc một snapshot tổng hợp.

**Khác biệt quan trọng:**

- `PFCOUNT key1 key2` tính ước lượng hợp **mà không cần tạo một destination HLL cố định**.
- `PFMERGE dest key1 key2` **ghi** kết quả hợp vào `dest`, có thay đổi trạng thái Redis.

Redis coi **destination đang tồn tại cũng là một nguồn đóng góp** khi merge. Vì vậy, nếu một destination chứa dữ liệu cũ, không nên dùng lại nó để tạo “báo cáo tháng mới” mà không xác định ý nghĩa của dữ liệu cũ. Muốn một snapshot hoàn toàn từ nguồn hiện tại, hãy dùng destination mới riêng biệt hoặc dọn destination cũ theo quy trình kiểm soát được.

## 5. HyperLogLog và Redis Set khác nhau thế nào?

Redis Set cũng có thể đếm người dùng phân biệt:

~~~bash
SADD exact:visitors user-A user-B user-A user-C
SCARD exact:visitors
SISMEMBER exact:visitors user-B
SMEMBERS exact:visitors
SREM exact:visitors user-B
~~~

Redis Set lưu **member thực**. Vì vậy, nó trả được số lượng chính xác, kiểm tra thành viên, liệt kê, xóa riêng user và thực hiện các phép tập hợp.

HyperLogLog:

~~~bash
PFADD approx:visitors user-A user-B user-A user-C
PFCOUNT approx:visitors
~~~

chỉ trả về thống kê gần đúng; nó không có `SISMEMBER` hay `SREM` tương đương theo từng phần tử.

| Nhu cầu | Redis Set | Redis HyperLogLog |
|---|---|---|
| Số phần tử phân biệt | **Chính xác** qua `SCARD` | **Ước lượng** qua `PFCOUNT` |
| Kiểm tra một user đã xuất hiện? | Có, `SISMEMBER` | Không |
| Liệt kê user | Có, nhưng cần lưu ý độ lớn | Không |
| Xóa một user khỏi tập | Có, `SREM` | Không |
| Gộp dữ liệu nhiều tập | Có, phép hợp chính xác | Có, hợp thống kê |
| Bộ nhớ khi có nhiều triệu user | Tăng theo số member và kích thước ID | Gần mức cố định, khoảng 12 KiB cho sketch dense |
| Hỗ trợ báo cáo DAU/MAU gần đúng | Có nhưng có thể tốn nhiều bộ nhớ | Rất phù hợp khi sai số được chấp nhận |
| Phục vụ phân quyền/membership | Có thể là một nguồn dữ liệu | Không thích hợp |
| Dùng để giới hạn chính xác số suất | Có thể kết hợp logic atomic phù hợp | Không thích hợp |

**Chọn Redis Set khi cần biết “ai”. Chọn HyperLogLog khi chỉ cần ước lượng “bao nhiêu”.**

### 5.1. HyperLogLog không phải Bloom filter

Bloom filter cũng là cấu trúc xác suất, nhưng tập trung vào câu hỏi kiểu **“giá trị này có khả năng đã xuất hiện không?”**, với đặc tính false positive tùy cấu hình. HyperLogLog giải quyết một câu hỏi khác: **“ước lượng đã có bao nhiêu giá trị phân biệt?”**

Không dùng HyperLogLog để chặn đăng ký trùng hoặc kiểm tra token đã dùng. Đó là các bài toán membership/deduplication cần công cụ khác.

## 6. Spring Data Redis cung cấp HyperLogLogOperations

Spring Data Redis định nghĩa abstraction:

~~~java
HyperLogLogOperations<K, V>
~~~

Các generic:

- `K`: kiểu Redis key, thường là `String`.
- `V`: kiểu phần tử đưa vào HLL, có thể là `String` hoặc kiểu phù hợp serializer.

Ví dụ với `StringRedisTemplate`:

~~~java
import org.springframework.data.redis.core.HyperLogLogOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

HyperLogLogOperations<String, String> hll =
        stringRedisTemplate.opsForHyperLogLog();
~~~

Các phương thức chính:

| Spring Data Redis | Lệnh Redis tương ứng | Ý nghĩa |
|---|---|---|
| `add(key, values...)` | `PFADD` | Nạp một hoặc nhiều giá trị vào HLL |
| `size(keys...)` | `PFCOUNT` | Ước lượng cardinality của một key hoặc hợp nhiều key |
| `union(destination, sources...)` | `PFMERGE`, và có thể truy vấn kết quả | Lưu HLL hợp vào destination |
| `delete(key)` | `DEL` | Xóa toàn bộ HLL key |

Các phương thức lấy kết quả dạng `Long` khi sử dụng đồng bộ theo API thông thường. Kết quả có thể là `null` trong một số ngữ cảnh RedisTemplate như pipeline/transaction khi chưa trả kết quả trực tiếp; code nên biết ngữ cảnh và kiểu trả về.

### 6.1. Lớp bên dưới vẫn là Redis driver

~~~text
                Spring Boot Service
                         |
                         v
          StringRedisTemplate.opsForHyperLogLog()
                         |
                         v
             HyperLogLogOperations
                         |
                  RedisTemplate
                         |
              RedisConnectionFactory
                         |
                  Lettuce / Jedis
                         |
                         v
                    Redis Server
                  PFADD / PFCOUNT
                    / PFMERGE
~~~

Không có một HyperLogLog Java chứa toàn bộ user trong heap của ứng dụng. Spring Data Redis chuyển lệnh qua connection và Redis Server duy trì trạng thái HLL.

## 7. Chuẩn bị ứng dụng Spring Boot

Ví dụ sử dụng Spring Boot 3.x và Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

`application.yml` cho Redis Server chạy trên máy phát triển:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Redis Server phải được triển khai/khởi chạy riêng. Starter tạo hạ tầng client và tích hợp Spring Boot, **không tự khởi chạy Redis Server**.

Khi Spring Boot nằm trong Docker container, `localhost` là chính container Spring Boot; nếu Redis ở container khác, dùng hostname/service name phù hợp mạng Docker. Với Redis managed, bổ sung cấu hình xác thực/TLS và endpoint thật theo yêu cầu.

Đối với ví dụ đếm ID dạng chuỗi, `StringRedisTemplate` thuận tiện vì key và value được serialize thống nhất theo chuỗi. Với template tùy chỉnh, cần đảm bảo serializer cho các giá trị được đưa vào HLL **nhất quán giữa mọi lần ghi và mọi service**.

## 8. Ví dụ cơ bản: đếm visitor ID phân biệt trong một ngày

Ta thiết kế các key theo ngày:

~~~text
stats:uv:siteA:2026-11-11
stats:uv:siteA:2026-11-12
stats:uv:siteA:2026-11-13
~~~

Mỗi key là **một HyperLogLog**, lưu trạng thái ước lượng những visitor ID đã xuất hiện tại website đó trong một ngày.

### 8.1. Service với add() và size()

~~~java
package com.example.redislearning;

import java.time.Duration;
import java.time.LocalDate;
import java.util.Objects;

import org.springframework.data.redis.core.HyperLogLogOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DailyUniqueVisitorService {

    private static final Duration RETENTION =
            Duration.ofDays(45);

    private final StringRedisTemplate redis;
    private final HyperLogLogOperations<String, String> hll;

    public DailyUniqueVisitorService(StringRedisTemplate redis) {
        this.redis = redis;
        this.hll = redis.opsForHyperLogLog();
    }

    public void recordVisit(
            String siteId,
            String visitorId,
            LocalDate date) {

        Objects.requireNonNull(siteId);
        Objects.requireNonNull(visitorId);
        Objects.requireNonNull(date);

        String key = dailyKey(siteId, date);

        // PFADD: nạp định danh vào sketch.
        hll.add(key, visitorId);

        // TTL áp dụng cho toàn bộ HLL key.
        redis.expire(key, RETENTION);
    }

    public long estimateDailyUnique(
            String siteId,
            LocalDate date) {

        Long estimate = hll.size(dailyKey(siteId, date));

        if (estimate == null) {
            throw new IllegalStateException(
                    "Redis did not return an HLL estimate");
        }
        return estimate;
    }

    private String dailyKey(
            String siteId,
            LocalDate date) {

        return "stats:uv:" + siteId + ":" + date;
    }
}
~~~

Khi dùng service:

~~~java
LocalDate today = LocalDate.of(2026, 11, 12);

service.recordVisit("siteA", "visitor-A", today);
service.recordVisit("siteA", "visitor-B", today);
service.recordVisit("siteA", "visitor-A", today);
service.recordVisit("siteA", "visitor-C", today);

long estimatedUsers =
        service.estimateDailyUnique("siteA", today);

System.out.println("Estimated unique visitors: "
        + estimatedUsers);
~~~

Tham số `visitorId` nên là **định danh ổn định và đã được thiết kế theo chính sách riêng tư của hệ thống**, không tự suy luận rằng mọi lượt truy cập cùng IP đều là cùng một người. Trong một môi trường đa tenant, `siteId` cũng cần được kiểm tra/chuẩn hóa và phân quyền trước khi ghép vào tên key.

### 8.2. Vì sao không kiểm tra return value của add() để quyết định visitor mới?

Ví dụ sai về ngữ nghĩa:

~~~java
Long result = hll.add(key, visitorId);

if (Long.valueOf(1L).equals(result)) {
    // SAI: không được kết luận visitorId chắc chắn là người mới.
}
~~~

`add()` phản ánh việc các register thống kê có thay đổi hay không. Nó **không phải kiểm tra membership** và không phải số user mới đã thêm.

Cách đúng là **đọc `size(key)` cho một số đếm ước lượng**, không dùng `add()` làm công tắc bật ưu đãi “lần đầu truy cập”.

### 8.3. TTL với HyperLogLog

Trong ví dụ, sau khi PFADD, service gọi:

~~~java
redis.expire(key, RETENTION);
~~~

TTL được đặt cho **toàn bộ HLL key**, không cho từng visitor ID. Khi hết hạn, Redis xóa trạng thái HLL của ngày đó, và không còn số liệu cũ để hợp vào báo cáo.

**Lưu ý:** `hll.add(...)` và `redis.expire(...)` là **hai Redis command riêng**, không phải một transaction atomic. Nếu ghi thành công nhưng process crash trước khi đặt TTL, key có thể chưa có TTL. Khi TTL là ràng buộc vận hành bắt buộc, cần một cơ chế bảo đảm tương ứng: ví dụ quy trình cleanup theo prefix/khoảng thời gian hoặc script/transaction phù hợp với phiên bản Redis.

Ngoài ra, gọi `expire(key, RETENTION)` mỗi lần có event sẽ **làm mới TTL tính từ lần ghi mới nhất**. Nếu muốn tất cả sketch của ngày 12/11 đều hết hạn tại cùng một mốc lịch, hãy chọn `expireAt(...)` với thời điểm được tính từ ngày thống kê thay vì dùng TTL trượt.

## 9. Ước lượng unique users của nhiều ngày: không cộng số từng ngày

Đây là tình huống sử dụng HyperLogLog rất phổ biến.

Giả sử một hệ thống có:

~~~text
Ngày 11/11: A, B, C, D
Ngày 12/11: B, C, E
Ngày 13/11: C, F
~~~

Số phân biệt từng ngày:

~~~text
11/11: 4
12/11: 3
13/11: 2
~~~

Nếu cộng các con số:

~~~text
4 + 3 + 2 = 9
~~~

ta đang tính **tổng lượt người theo từng ngày**, không phải unique users trong cả khoảng ba ngày. Tập hợp thực tế là:

~~~text
{A, B, C, D, E, F} -> 6 người phân biệt
~~~

Với Redis HLL, dùng `PFCOUNT` trên nhiều key để ước lượng cardinality của **hợp các tập**.

### 9.1. Spring Data Redis: size(keys...)

~~~java
public long estimateThreeDayUnique(
        HyperLogLogOperations<String, String> hll) {

    Long estimate = hll.size(
            "stats:uv:siteA:2026-11-11",
            "stats:uv:siteA:2026-11-12",
            "stats:uv:siteA:2026-11-13"
    );

    if (estimate == null) {
        throw new IllegalStateException("Missing estimate");
    }
    return estimate;
}
~~~

Tương ứng:

~~~text
PFCOUNT stats:uv:siteA:2026-11-11
        stats:uv:siteA:2026-11-12
        stats:uv:siteA:2026-11-13
~~~

Lệnh trả **ước lượng hợp** trực tiếp. Không phải tạo một key `stats:uv:siteA:three-days` mới chỉ để trả kết quả một lần.

### 9.2. Tính unique visitors của cả tháng

Có thể sinh danh sách key theo từng ngày:

~~~java
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.HyperLogLogOperations;

public long estimateMonthlyUnique(
        HyperLogLogOperations<String, String> hll,
        String siteId,
        YearMonth month) {

    List<String> dayKeys = new ArrayList<>();

    for (int day = 1; day <= month.lengthOfMonth(); day++) {
        LocalDate date = month.atDay(day);
        dayKeys.add(
                "stats:uv:" + siteId + ":" + date
        );
    }

    Long estimate =
            hll.size(dayKeys.toArray(String[]::new));

    if (estimate == null) {
        throw new IllegalStateException(
                "No monthly unique estimate returned");
    }
    return estimate;
}
~~~

Khi một số key ngày chưa tồn tại, Redis có thể xem chúng như HLL rỗng cho phép ước lượng hợp. Tuy nhiên, **mất sketch của một ngày đã từng có dữ liệu không giống một ngày không có traffic**: nếu sketch cũ đã hết TTL trước khi báo cáo tháng được tính, kết quả sẽ **thiếu dữ liệu không thể suy ra lại** chỉ từ các sketch còn tồn tại.

Vì thế, retention của daily HLL phải đủ dài cho tất cả báo cáo theo tuần/tháng hoặc cần lưu bản tổng hợp theo một lịch chạy được quản lý.

### 9.3. Điều kiện để hợp có ý nghĩa

Các HLL chỉ cho số unique đúng về mặt định nghĩa khi **cùng thực thể được biểu diễn bằng cùng một định danh** trong mọi key nguồn.

Ví dụ, nếu `visitor-A` được mã hóa thành ID khác nhau mỗi ngày, phép hợp sẽ xem đó là **hai phần tử khác nhau**, dẫn tới số unique của cả tháng bị đếm cao. Nếu muốn dùng ID băm, cách chuẩn hóa và salt phải giữ ổn định trong **khoảng báo cáo cần hợp** và phù hợp chính sách bảo vệ dữ liệu.

Đừng trộn:

- ID user đăng nhập và IP client không có quy tắc ánh xạ.
- UUID được sinh mới cho mỗi request (sẽ gần giống đếm lượt, không đếm user).
- ID đã đổi thuật toán hash giữa tháng mà không có kế hoạch chuyển đổi.

HyperLogLog ước lượng rất tốt **theo định nghĩa “phần tử phân biệt” mà bạn đưa vào**; nó không tự biết danh tính người dùng thực ngoài đời.

## 10. Tạo một key tổng hợp bằng union()

Khi báo cáo theo tháng được truy cập thường xuyên, có thể lưu một HLL tổng hợp:

~~~text
Daily sketches:
  stats:uv:siteA:2026-11-01
  stats:uv:siteA:2026-11-02
  ...
  stats:uv:siteA:2026-11-30

Monthly sketch:
  stats:uv:siteA:monthly:2026-11
~~~

### 10.1. API union(destination, sources...)

~~~java
import org.springframework.data.redis.core.HyperLogLogOperations;

String destination = "stats:uv:siteA:monthly:2026-11";

Long count = hll.union(
        destination,
        "stats:uv:siteA:2026-11-11",
        "stats:uv:siteA:2026-11-12"
);
~~~

`union(...)` dùng cơ chế hợp nhất HLL tương ứng với `PFMERGE`. Destination chứa **trạng thái thống kê hợp**, từ đó có thể truy vấn bằng:

~~~java
Long estimatedMonthly =
        hll.size("stats:uv:siteA:monthly:2026-11");
~~~

### 10.2. Không tái sử dụng destination chứa dữ liệu không liên quan

`PFMERGE` có thể tính cả trạng thái HLL đã có ở **destination**. Vì vậy:

~~~text
Destination trước đó: HLL của tháng 10
Sources mới: HLL của tháng 11

PFMERGE destination sources...
    -> nguy cơ tạo hợp tháng 10 + tháng 11
       thay vì chỉ tháng 11
~~~

Nếu muốn **snapshot chỉ gồm nguồn của một tháng**, nên dùng destination mới không có dữ liệu trước đó. Khi cần thay thế bản báo cáo cũ, hãy thiết kế cách rebuild riêng: ví dụ xây sketch mới với tên key tạm rồi chuyển sang key chính sau khi hoàn tất, hoặc xóa destination cũ một cách có kiểm soát trước khi merge.

**Không xóa destination rồi merge một cách tùy tiện trên key đang được request khác đọc**, vì có thể xuất hiện khoảng thời gian key biến mất hoặc có dữ liệu chưa đúng kỳ vọng. Trong Redis Cluster, thao tác nhiều key và đổi tên key còn cần lưu ý ràng buộc hash slot.

### 10.3. Tổng hợp là snapshot tại thời điểm chạy

Nếu sau khi merge, một daily HLL tiếp tục nhận visitor mới, **monthly HLL không tự cập nhật theo daily HLL**. Phải:

- Chạy merge lại theo lịch,
- Hoặc cập nhật sketch tổng hợp theo luồng sự kiện được thiết kế riêng,
- Hoặc truy vấn `size(dailyKeys...)` trực tiếp mỗi lần cần báo cáo.

Chọn cách nào tùy độ mới dữ liệu, số lượng key, chi phí query và yêu cầu vận hành. Mỗi phương án cần định nghĩa rõ **timestamp báo cáo**, vì “monthly unique” ở 10:00 và 10:05 có thể khác nhau trong một tháng đang diễn ra.

## 11. Redis Cluster và phép hợp HLL nhiều key

Trong Redis Cluster, mỗi Redis key thuộc một **hash slot**. Các lệnh Redis nhiều key như `PFCOUNT key1 key2` hoặc `PFMERGE dest source1 source2` phải tuân theo quy tắc cùng slot khi được thực thi như một multi-key command trên cluster.

Ví dụ các key sau có thể nằm ở **nhiều slot khác nhau**:

~~~text
stats:uv:siteA:2026-11-11
stats:uv:siteA:2026-11-12
stats:uv:siteA:monthly:2026-11
~~~

Nếu cần hợp trực tiếp trên Redis Cluster, có thể chọn **hash tag**:

~~~text
stats:uv:{siteA}:2026-11-11
stats:uv:{siteA}:2026-11-12
stats:uv:{siteA}:monthly:2026-11
~~~

Phần trong ngoặc nhọn là hash tag chung `siteA`, đưa các key này về cùng slot theo quy tắc Redis Cluster.

Tuy nhiên, **đây là một đánh đổi**:

- Thuận tiện cho phép hợp nhiều key theo site.
- Nhưng mọi HLL của cùng site tập trung lên một slot, có thể tạo điểm nóng nếu site có lưu lượng cực lớn.
- Nếu có quá nhiều site với tải khác biệt, phải tính chiến lược sharding và tổng hợp theo cấp phù hợp.

Không có thiết kế tên key nào đồng thời tối đa hóa cả **khả năng tách shard** và **mọi phép hợp atomic giữa key bất kỳ**. Hãy xuất phát từ truy vấn cần thiết và topology thực tế.

## 12. HyperLogLog là một Redis String có định dạng đặc biệt

Một chi tiết dễ gây nhầm: Redis triển khai HyperLogLog bằng **giá trị dạng String được mã hóa theo định dạng riêng**. Vì vậy, lệnh `TYPE` có thể trả `string` cho một HLL key:

~~~bash
PFADD demo:uv user-A user-B
TYPE demo:uv
~~~

Kết quả:

~~~text
string
~~~

Điều này **không có nghĩa bạn nên đọc HLL bằng `StringRedisTemplate.opsForValue().get()` rồi xem nội dung như một chuỗi văn bản bình thường**. Payload bên trong là cấu trúc nhị phân mà Redis dùng cho HLL.

Các anti-pattern:

~~~java
// Sai về thiết kế: HLL không chứa danh sách visitor dạng chuỗi.
String raw = redis.opsForValue().get("demo:uv");

// Sai về thiết kế: SET sẽ ghi đè cấu trúc HLL bằng String thông thường.
redis.opsForValue().set("demo:uv", "some text");
~~~

Ghi đè bằng `SET` có thể làm `PFCOUNT` hoặc `PFADD` sau đó báo lỗi do dữ liệu không còn là HyperLogLog hợp lệ. Dùng namespace riêng cho HLL, ví dụ `stats:hll:...`, để tránh nhầm với String counter hoặc Set.

### 12.1. HLL không phải cấu trúc có thể đọc ra danh sách

Không có API HLL tương đương `SMEMBERS` của Set. Những câu hỏi sau **không thể được trả lời chỉ từ HLL**:

- “Những user cụ thể nào đã truy cập hôm nay?”
- “User 42 đã truy cập chưa?”
- “Hãy xóa user 42 khỏi thống kê.”
- “Những user nào có mặt hôm qua nhưng không có mặt hôm nay?”

Muốn trả lời những câu hỏi đó, cần nguồn dữ liệu khác như Set, database hoặc event log. HLL có thể tồn tại **song song** với nguồn dữ liệu khác để cung cấp số thống kê nhanh và tiết kiệm bộ nhớ.

## 13. TTL, retention và quyền xóa dữ liệu

### 13.1. TTL của toàn key

HLL là một Redis key nên có thể:

~~~bash
EXPIRE stats:uv:siteA:2026-11-12 3888000
TTL stats:uv:siteA:2026-11-12
DEL stats:uv:siteA:2026-11-12
~~~

`3888000` giây tương ứng 45 ngày trong ví dụ. `EXPIRE` và `DEL` tác động **toàn bộ HLL key**, không phải một visitor ID.

Với `StringRedisTemplate`:

~~~java
redis.expire(
        "stats:uv:siteA:2026-11-12",
        Duration.ofDays(45)
);
~~~

Nếu chỉ cần xóa toàn bộ sketch:

~~~java
hll.delete("stats:uv:siteA:2026-11-12");
~~~

Lệnh xóa toàn key có thể dùng API khác của template tương đương, chẳng hạn `redis.delete(key)`.

### 13.2. Không xóa một phần tử riêng lẻ khỏi HyperLogLog

Do Redis không giữ lại tập đầy đủ các ID trong HLL, không có lệnh tiêu chuẩn để **rút một visitor đã thêm khỏi sketch** và khôi phục chính xác register trước đó.

Nếu nghiệp vụ yêu cầu xóa ảnh hưởng của một user khỏi thống kê:

1. Có thể cần **dựng lại HLL** từ nguồn sự kiện còn lưu, sau khi loại user đó.
2. Hoặc thiết kế bucket/aggregate nhỏ hơn để xóa theo nhóm/khoảng thời gian.
3. Hoặc chọn cấu trúc chính xác có hỗ trợ remove, chẳng hạn Set, nếu nhu cầu xóa cá nhân quan trọng hơn bộ nhớ.

Không nên khẳng định rằng HLL “không chứa thông tin cá nhân” chỉ vì nó không liệt kê được user. ID đưa vào, cách băm và metadata có thể liên quan đến chính sách riêng tư; yêu cầu pháp lý/bảo mật cần đánh giá trên toàn hệ thống.

### 13.3. Retention phải đi cùng cửa sổ báo cáo

Nếu báo cáo MAU của tháng 11 cần chạy vào đầu tháng 12, các HLL theo ngày của tháng 11 phải còn tồn tại khi hệ thống tính báo cáo hoặc đã có một snapshot tổng hợp đúng.

Một tình huống sai:

~~~text
HLL daily TTL = 7 ngày
Báo cáo unique users cả tháng được chạy ngày 01/12

=> Nhiều HLL đầu tháng 11 đã hết hạn.
=> Kết quả hợp chỉ còn dữ liệu của một phần tháng.
~~~

Do đó, chính sách xóa nên được thiết kế dựa trên **thời gian tính báo cáo và khả năng tái tính**, không chỉ nhìn vào mức bộ nhớ HLL nhỏ mà đặt TTL ngẫu nhiên.

## 14. Bộ nhớ ít không có nghĩa mọi phép đếm đều miễn phí

Một HLL nhỏ giúp giảm chi phí lưu danh sách user, nhưng ứng dụng vẫn cần cân nhắc:

- **Số lượng HLL key**: nhiều triệu key khác nhau vẫn tạo overhead keyspace, metadata và expiration.
- **Số key trong một phép hợp**: `PFCOUNT` với rất nhiều HLL nguồn hoặc `PFMERGE` cần xử lý sketch của từng key, không có chi phí cố định bất kể số nguồn.
- **Số lệnh PFADD**: nếu mỗi request gửi một lệnh riêng, tổng lượng traffic Redis vẫn tăng theo số request.
- **Hot key**: một HLL cho toàn website đang nhận lượng lớn PFADD có thể trở thành điểm tập trung tải ở một Redis slot.
- **Serialization**: chuỗi visitor ID dài và cách tạo key có thể tăng băng thông.
- **Redis topology**: shard/cluster ảnh hưởng chiến lược đặt tên key và union.

Ví dụ hệ thống có:

~~~text
100 website
× 365 ngày
= 36.500 HLL keys/năm
~~~

Đây là số key có thể quản lý bằng retention phù hợp. Nhưng nếu tạo mỗi HLL cho từng kết hợp `site × URL × campaign × device × minute`, cardinality **của chính keyspace** có thể bùng nổ dù mỗi HLL chỉ dùng ít bộ nhớ.

Vì vậy, **đừng tối ưu mỗi sketch mà bỏ qua tổng số chiều phân tích và số lượng key**.

## 15. Thiết kế định danh visitor có ảnh hưởng trực tiếp đến số đếm

HyperLogLog không tự biết “người” là ai. Nó chỉ nhận các giá trị `V` mà ứng dụng gửi.

Giả sử bạn dùng:

~~~text
visitorId = userId đăng nhập
~~~

thì thước đo gần với **số tài khoản đăng nhập phân biệt**. Nếu dùng:

~~~text
visitorId = cookieId
~~~

thì thước đo gần với **số trình duyệt hoặc thiết bị có cookie phân biệt**, không nhất thiết là số người thật. Nếu dùng:

~~~text
visitorId = IP address
~~~

thì nhiều người sau một NAT có thể bị tính là một, còn một người đổi IP có thể bị tính nhiều lần.

**Định nghĩa metric trước khi chọn HLL:**

| Metric muốn báo cáo | Định danh đầu vào nên cân nhắc | Điểm cần thận trọng |
|---|---|---|
| Unique logged-in users | User ID ổn định | Một user có thể đăng nhập nhiều thiết bị nhưng vẫn là một |
| Unique browser sessions | Session/cookie ID | Một user có thể có nhiều session |
| Unique devices gần đúng | Thiết bị hoặc installation ID theo chính sách cho phép | Reset ID, chia sẻ thiết bị, quyền riêng tư |
| Unique API clients | Client/application ID | Không đồng nghĩa số người dùng |
| Unique products được xem | Product ID | Đếm sản phẩm khác nhau, không phải người |
| Unique order IDs được xử lý | Order ID | HLL chỉ cho thống kê; không chứng minh xử lý từng order |

Nếu phải băm ID trước khi lưu, băm phải **deterministic** cho cùng thực thể trong cùng cửa sổ thống kê. Thay đổi salt hoặc quy tắc canonicalization giữa các ngày có thể khiến HLL hợp tháng tăng sai.

Hãy thiết kế thu thập và lưu metric tuân thủ quy định bảo vệ dữ liệu. Không log raw visitor/token ID chỉ để debug `PFADD` và không xem hashed identifier là hoàn toàn vô danh trong mọi bối cảnh.

## 16. Đồng thời (concurrency) và tính nhất quán

### 16.1. PFADD từ nhiều instance

Nhiều Spring Boot instance có thể đồng thời gọi:

~~~text
Instance A -> PFADD uv:today visitor-42
Instance B -> PFADD uv:today visitor-42
Instance C -> PFADD uv:today visitor-99
~~~

Các lệnh Redis được xử lý theo ngữ nghĩa atomic của từng command. Việc cùng visitor xuất hiện hai lần không làm HLL cố tình lưu hai member như một List.

Nhưng cần phân biệt:

- **Đưa cùng giá trị vào sketch nhiều lần**: trạng thái HLL không có ý định đếm lặp.
- **Producer retry một event với ID mới**: HLL thấy hai giá trị khác nhau và có thể làm tăng ước lượng cardinality.
- **PFADD rồi EXPIRE**: vẫn là hai command, không atomic theo nhóm.
- **Cập nhật HLL rồi ghi database**: không tự là transaction phân tán.

### 16.2. Thời điểm đọc ảnh hưởng kết quả

Nếu traffic đang tiếp tục:

~~~text
10:00:00  PFCOUNT -> estimate X
10:00:01  thêm nhiều visitor mới
10:00:02  PFCOUNT -> estimate Y
~~~

Hai con số có thể khác nhau. Một báo cáo realtime nên ghi rõ **thời điểm/cửa sổ đo**, không yêu cầu một số cố định mãi trong khi dữ liệu đang được ghi.

### 16.3. Không dùng HLL để ngăn xử lý nghiệp vụ trùng

Anti-pattern:

~~~java
Long modified = hll.add("processed:orders", orderId);

if (Long.valueOf(1L).equals(modified)) {
    // SAI: không có bảo đảm đây là order chưa xử lý.
    processPayment(orderId);
}
~~~

Việc thanh toán, khấu trừ tồn kho, cấp quyền hoặc xác định “user được thưởng lần đầu” phải dùng dữ liệu và thao tác có tính đúng đắn phù hợp: unique constraint, transaction, Redis Set với điều kiện atomic hoặc nguồn trạng thái nghiệp vụ đáng tin cậy.

HyperLogLog phù hợp để **ước lượng bao nhiêu order ID khác nhau đã xuất hiện**, không phù hợp để **chặn một order ID xử lý hai lần**.

## 17. Tình huống thực tế: DAU, WAU, MAU

Trong phân tích sản phẩm, ta thường gặp:

- **DAU (Daily Active Users)**: số user phân biệt hoạt động trong một ngày.
- **WAU (Weekly Active Users)**: số user phân biệt hoạt động trong một tuần.
- **MAU (Monthly Active Users)**: số user phân biệt hoạt động trong một tháng.

Một cách lưu theo ngày:

~~~text
stats:dau:appA:2026-11-10
stats:dau:appA:2026-11-11
stats:dau:appA:2026-11-12
...
~~~

Khi một user hoạt động trong ngày 12:

~~~bash
PFADD stats:dau:appA:2026-11-12 user-42
~~~

DAU ngày 12:

~~~bash
PFCOUNT stats:dau:appA:2026-11-12
~~~

WAU trong tuần:

~~~text
PFCOUNT HLL_day1 HLL_day2 ... HLL_day7
~~~

MAU trong tháng:

~~~text
PFCOUNT HLL_day1 HLL_day2 ... HLL_day30
~~~

### 17.1. Vì sao WAU không phải tổng DAU?

Một user hoạt động cả bảy ngày:

~~~text
DAU mỗi ngày: 1
Tổng 7 DAU: 7
WAU phân biệt: 1
~~~

Tương tự, **MAU không phải tổng của DAU**. Dùng `size(keys...)` hoặc `PFMERGE` để hợp tập các sketch theo ngày nếu định nghĩa “active” và định danh người dùng thống nhất.

### 17.2. Tại sao có thể vẫn cần event log?

HLL giúp báo cáo nhanh với bộ nhớ nhỏ, nhưng không thể trả lại danh sách user hoạt động. Nếu sau đó business hỏi:

> “Những user nào có mặt tuần trước nhưng không quay lại tuần này?”

HLL không đủ. Cần dữ liệu ở mức từng user (ví dụ event log, data warehouse hoặc Set khi quy mô phù hợp). Một kiến trúc thường có:

~~~text
User activity events
       |
       +--> Redis HyperLogLog -> dashboard DAU/WAU/MAU gần realtime
       |
       '--> Event storage / warehouse -> phân tích cohort, audit,
                                      truy vấn chính xác và rebuild
~~~

HLL có thể là **materialized approximation**, không bắt buộc là nguồn dữ liệu duy nhất.

## 18. Kiểm tra thao tác bằng redis-cli

Trên Redis Server dành cho môi trường học, thử:

### Bước 1: tạo HLL mới

~~~bash
DEL lab:hll:day1 lab:hll:day2 lab:hll:union

PFADD lab:hll:day1 alice bob charlie
PFADD lab:hll:day2 bob charlie diana
~~~

### Bước 2: đọc ước lượng từng ngày

~~~bash
PFCOUNT lab:hll:day1
PFCOUNT lab:hll:day2
~~~

Với tập dữ liệu rất nhỏ như ví dụ, kết quả có thể bằng số phân biệt thực tế, nhưng **không lấy một lần thử để kết luận HyperLogLog luôn chính xác**.

### Bước 3: đọc số phân biệt của hợp hai ngày

~~~bash
PFCOUNT lab:hll:day1 lab:hll:day2
~~~

Hai ngày có `bob` và `charlie` trùng nhau. Vì vậy, khái niệm cần kiểm chứng là **hợp**, không phải cộng số mỗi ngày.

### Bước 4: tạo HLL tổng hợp

~~~bash
PFMERGE lab:hll:union lab:hll:day1 lab:hll:day2
PFCOUNT lab:hll:union
~~~

Quan sát `PFCOUNT` của key tổng hợp và so với phép hợp ở bước 3.

### Bước 5: xem kiểu dữ liệu và TTL

~~~bash
TYPE lab:hll:union
EXPIRE lab:hll:union 120
TTL lab:hll:union
~~~

`TYPE` có thể hiển thị `string` do HyperLogLog được Redis mã hóa trong một String đặc biệt.

### Bước 6: thêm trùng và xóa toàn bộ

~~~bash
PFADD lab:hll:day1 alice
PFCOUNT lab:hll:day1
DEL lab:hll:day1 lab:hll:day2 lab:hll:union
~~~

Lưu ý lệnh `PFADD` không cho biết chắc chắn alice là phần tử mới hay cũ qua giá trị 0/1; đó là thông tin về cập nhật register. Khi xong nên dọn các key lab để tránh tồn tại dữ liệu thử nghiệm.

## 19. Ví dụ integration test Spring Data Redis

Ngoài redis-cli, có thể viết một integration test thực sự kết nối Redis. Ví dụ dự án đã có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Test minh họa:

~~~java
package com.example.redislearning;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.HyperLogLogOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class HyperLogLogIntegrationTest {

    @Autowired
    private StringRedisTemplate redis;

    @Test
    void duplicateValueDoesNotChangeTheSketch() {
        String key = "test:hll:" + UUID.randomUUID();
        HyperLogLogOperations<String, String> hll =
                redis.opsForHyperLogLog();

        try {
            hll.add(key, "alice", "bob", "charlie");
            Long before = hll.size(key);
            assertNotNull(before);
            assertTrue(before > 0);

            // Cùng các input đã thêm, trạng thái HLL không đổi.
            hll.add(key, "alice", "bob", "charlie");
            Long after = hll.size(key);
            assertEquals(before, after);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Test **không assert** rằng ba phần tử nhất định phải trả chính xác `3`, vì đó không phải contract của một cấu trúc ước lượng. Thay vào đó, nó kiểm tra một thuộc tính phù hợp: thêm lại **đúng các phần tử cũ** không làm thay đổi trạng thái HLL và ước lượng.

Đây là **integration test cần Redis Server thật** (hoặc Redis test container tương thích) và cấu hình kết nối riêng; không nên trỏ test vào Redis production. Bài học không yêu cầu kết nối Redis để đọc hiểu code.

## 20. Dùng HLL cùng RedisTemplate cần chú ý serializer

`StringRedisTemplate` thường là lựa chọn dễ quan sát vì cùng định danh Java sẽ được serialize thành cùng bytes ở đầu vào Redis.

Tuy nhiên, nếu một ứng dụng ghi:

~~~text
PFADD stats:uv:today "user-42"
~~~

còn một ứng dụng khác serialize một object `UserId(42)` theo JSON hoặc JDK serialization, Redis có thể nhận **byte sequences khác nhau**. HLL sẽ coi đó là những giá trị khác nhau nếu bytes khác nhau, ngay cả khi về mặt nghiệp vụ là cùng một user.

Vì vậy:

- Chọn cách canonicalize ID (ví dụ chuỗi dạng `user:<stable-id>`) thống nhất.
- Đồng bộ serializer giữa các service ghi vào cùng HLL.
- Nếu đổi thuật toán hash/pseudonymization, cần kế hoạch chuyển tiếp cho giai đoạn báo cáo giao nhau.
- Tránh trộn nhiều loại định danh không có ngữ nghĩa tương đồng.

### 20.1. Namespace cho HLL phải rõ ràng

Ví dụ:

~~~text
stats:hll:uv:appA:2026-11-12
stats:counter:pageviews:appA:2026-11-12
stats:set:vip-users:appA
~~~

Ba key có mục đích và Redis command khác nhau. Mặc dù HLL có `TYPE string`, **không được sử dụng lẫn các key HLL với String counter**; thao tác `SET`/`INCR` trên cùng tên key có thể phá cấu trúc HLL hoặc gây lỗi.

## 21. Khi nào nên dùng HyperLogLog, khi nào không?

### 21.1. Nên cân nhắc HyperLogLog

- **Unique visitors** theo website, ngày, tuần, tháng.
- **Số thiết bị khác nhau** gửi telemetry vào một hệ thống, với định danh và chính sách riêng tư phù hợp.
- **Số sản phẩm khác nhau** đã được xem trong một chiến dịch.
- **Số IP/client ID gần đúng** phục vụ thống kê hoặc capacity planning, với nhận thức rõ hạn chế của cách định danh.
- **Ước lượng cardinality** trên nhiều phân vùng thời gian khi không muốn lưu từng ID trong Redis.
- **Dashboard xu hướng** nơi sai số xác suất nhỏ được chấp nhận.

### 21.2. Không nên dùng HyperLogLog làm nguồn quyết định chính xác

- Kiểm tra một user đã được cấp quyền chưa.
- Chống xử lý trùng payment/order ID.
- Đếm chính xác số ghế/suất đăng ký còn lại.
- Liệt kê user phân biệt để gửi email.
- Xóa một ID khỏi tập và cập nhật chính xác số đếm.
- Tính tiền theo số user phân biệt khi hợp đồng yêu cầu con số được đối soát.
- Tính hiệu của hai tập để tìm user churn cụ thể.

Những trường hợp này cần tập dữ liệu thật, dữ liệu quan hệ, Set hoặc các cấu trúc phù hợp hơn.

### 21.3. Một quy trình chọn nhanh

~~~text
            Cần đếm số giá trị phân biệt?
                          |
                 +--------+--------+
                 |                 |
                Không              Có
                 |                 |
             Counter,              v
             Stream...      Cần kết quả chính xác?
                               /           \
                             Có             Không
                             |                |
                             v                v
                       Redis Set /        Cần biết từng
                       database           phần tử hoặc xóa
                                           từng phần tử?
                                          /           \
                                        Có             Không
                                        |                |
                                        v                v
                                    Redis Set /      Redis HyperLogLog
                                    database         (ước lượng)
                                         \               /
                                          \             /
                                           v           v
                                    Thiết kế ID, TTL,
                                retention và khả năng rebuild
~~~

Không có một cấu trúc duy nhất tối ưu cho tất cả bài toán. HLL mạnh nhất khi dữ liệu rất lớn, số đếm chỉ cần gần đúng và việc lưu member riêng lẻ không đem lại giá trị tương xứng.

## 22. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `PFCOUNT` khác số đếm trong database | Bản chất ước lượng, định nghĩa ID khác nhau, trễ dữ liệu hoặc thiếu ngày | Xác định sai số chấp nhận, so cùng population/cửa sổ |
| Cộng DAU ra MAU quá cao | User xuất hiện ở nhiều ngày bị đếm lặp | Dùng `PFCOUNT` nhiều key hoặc `PFMERGE` |
| Thêm ID mới nhưng `PFADD` trả 0 | Không register nào thay đổi | Không dùng return value làm membership check |
| `PFCOUNT` trả 0 | Key chưa tồn tại, hết TTL hoặc chưa có dữ liệu | Kiểm tra key, thời gian và đường ghi |
| Dữ liệu tháng trước làm bẩn thống kê tháng này | `PFMERGE` tái sử dụng destination cũ | Tạo destination sạch/đúng kỳ, thiết kế rebuild |
| Monthly HLL không tăng dù daily HLL có thêm dữ liệu | Destination merge là snapshot | Merge lại hoặc cập nhật summary theo event |
| Lỗi khi PFCOUNT một key đã từng SET text | Key không có encoding HLL hợp lệ | Tách namespace HLL, khôi phục/rebuild |
| Redis Cluster báo CROSSSLOT cho phép hợp nhiều key | Các key nằm ở hash slot khác nhau | Thiết kế hash tag/co-location có chủ đích |
| Không tìm thấy danh sách visitor trong HLL | HLL không lưu member đầy đủ | Lưu nguồn event/Set/database nếu cần |
| Không xóa được riêng một visitor | Không có thao tác remove member HLL | Rebuild hoặc thay đổi kiến trúc dữ liệu |
| Các user giống nhau giữa hai service lại bị đếm khác | Serializer hoặc canonicalization khác nhau | Đồng bộ ID và byte encoding |
| HLL của đầu tháng biến mất | TTL ngắn hơn cửa sổ tính báo cáo | Điều chỉnh retention hoặc lưu summary đáng tin cậy |
| Redis memory vẫn lớn dù dùng HLL | Tạo quá nhiều HLL key, hot key hoặc overhead khác | Đo số key, TTL, cardinality chiều phân tích |
| Test kiểm tra đúng chính xác count=100 bị không ổn định | Test áp đặt độ chính xác tuyệt đối lên HLL | Test invariants/đánh giá sai số thống kê, không assert bằng tuyệt đối |

### 22.1. Quan sát Redis mà không đọc raw HLL

Có thể dùng:

~~~bash
PFCOUNT stats:hll:uv:appA:2026-11-12
TYPE stats:hll:uv:appA:2026-11-12
TTL stats:hll:uv:appA:2026-11-12
MEMORY USAGE stats:hll:uv:appA:2026-11-12
~~~

`MEMORY USAGE` giúp ước lượng bộ nhớ Redis đang dùng cho key ở mức Redis, có thể khác con số 12 KiB do overhead và encoding. Không cần dùng `GET` để đọc binary payload nhằm hiểu số lượng unique.

Theo dõi ở ứng dụng:

- Số lần PFADD theo site/ngày.
- Kết quả PFCOUNT theo cửa sổ thống kê.
- Tần suất chạy phép hợp và thời gian phản hồi.
- Số HLL key còn giữ và TTL của chúng.
- Redis CPU, memory, hot key, network, connection timeout.
- Độ đầy đủ của dữ liệu nguồn khi ingest từ sự kiện.

Nếu cần đánh giá độ chính xác, có thể so sánh kết quả HLL với **nguồn exact trên một mẫu đại diện hoặc khoảng thời gian có thể tính chính xác**, thay vì giả định một kết quả PFCOUNT luôn nằm trong một giới hạn sai số cứng.

## 23. Bài tập tự luyện

### Bài 1 — Đếm user phân biệt ở hai ngày

Nhập:

~~~text
Ngày 1: A, B, C, D, D
Ngày 2: B, D, E, F
~~~

Thực hiện:

1. Tạo hai HLL `practice:hll:day1` và `practice:hll:day2`.
2. Dùng `PFADD` để thêm các ID.
3. Gọi `PFCOUNT` cho mỗi ngày.
4. Gọi `PFCOUNT practice:hll:day1 practice:hll:day2`.
5. Giải thích vì sao không lấy tổng kết quả hai ngày làm số unique hai ngày.

### Bài 2 — So sánh Set và HLL

Trên môi trường Redis test:

~~~bash
SADD practice:set alice bob charlie alice
SCARD practice:set
SISMEMBER practice:set alice

PFADD practice:hll alice bob charlie alice
PFCOUNT practice:hll
~~~

Trả lời:

- Cấu trúc nào biết chắc `alice` có phải member không?
- Cấu trúc nào có thể xóa riêng `bob`?
- Nếu thêm một triệu ID khác nhau, sự khác biệt bộ nhớ và khả năng liệt kê là gì?

### Bài 3 — Thiết kế báo cáo theo tuần

Một website muốn DAU và WAU gần đúng. Vẽ key pattern, TTL, thời điểm tạo snapshot tuần, và cách xử lý tình huống:

- User đăng nhập nhiều lần trong ngày.
- User hoạt động nhiều ngày.
- Báo cáo được tính lại sau vài ngày.
- Một daily sketch hết TTL trước lúc tính WAU.

### Bài 4 — Redis Cluster và union

Giả sử:

~~~text
stats:uv:siteA:2026-11-11
stats:uv:siteA:2026-11-12
~~~

Cần thực hiện một lệnh PFCOUNT nhiều key trong Redis Cluster. Đề xuất tên key dùng hash tag chung, rồi giải thích đánh đổi khi một site trở nên quá nóng.

### Bài 5 — Phân tích sự khác biệt giữa thống kê và nghiệp vụ

Một hệ thống muốn “mỗi user chỉ được nhận voucher một lần”, đồng thời muốn biết gần đúng “có bao nhiêu user đã nhận voucher”.

- Có nên dùng cùng một HLL để thực thi cả hai yêu cầu không?
- Dữ liệu nào cần chính xác để chống phát voucher trùng?
- HLL có thể được cập nhật ở bước nào để phục vụ dashboard?
- Nếu cập nhật Redis thống kê thất bại nhưng phát voucher thành công, phải xử lý eventual consistency thế nào?

## 24. Câu hỏi củng cố

**1. HyperLogLog giải quyết vấn đề gì?**

Ước lượng số lượng phần tử phân biệt (cardinality) mà không cần lưu toàn bộ danh sách phần tử.

**2. Redis HyperLogLog có bộ nhớ tăng theo từng user như Set không?**

Không theo cùng cách. HLL lưu các register thống kê, thường ở mức nhỏ và gần cố định, khoảng 12 KiB cho dạng dense, trong khi Set lưu từng member.

**3. Sai số 0,81% nghĩa là kết quả chắc chắn nằm trong ±0,81% không?**

Không. Đó là sai số chuẩn thống kê thường được nêu cho Redis HLL, không phải giới hạn tuyệt đối cho mọi lần đếm.

**4. PFADD trả 1 có nghĩa ID mới hoàn toàn chưa?**

Không. Nó cho biết ít nhất một register thay đổi, không xác nhận membership hoặc mức tăng chính xác của cardinality.

**5. Spring Data Redis dùng API nào để thêm và đếm?**

`redis.opsForHyperLogLog().add(key, values...)` và `redis.opsForHyperLogLog().size(keys...)`.

**6. Vì sao MAU không phải tổng DAU?**

Vì cùng một user có thể xuất hiện trong nhiều ngày. MAU cần cardinality của **hợp** các tập user theo ngày, không cộng các số đếm.

**7. PFCOUNT nhiều key và PFMERGE khác nhau thế nào?**

PFCOUNT nhiều key trả ước lượng hợp trực tiếp. PFMERGE lưu HLL hợp vào destination key để dùng lại.

**8. Vì sao không nên merge vào một destination có dữ liệu không liên quan?**

Destination hiện có cũng có thể đóng góp vào phép hợp, làm số liệu chứa cả dữ liệu cũ. Cần destination đúng kỳ và chiến lược rebuild.

**9. Có thể dùng HLL để biết user-42 đã xem sản phẩm chưa?**

Không. HLL không cung cấp membership check; dùng Set/database hoặc cấu trúc khác theo yêu cầu chính xác.

**10. Có thể xóa user-42 khỏi HLL không?**

Không có lệnh remove member HLL thông thường. Cần nguồn dữ liệu để rebuild hoặc thiết kế bucket/aggregate khác.

**11. Tại sao Redis TYPE của HLL có thể là string?**

Vì Redis lưu HLL trong một String mã hóa đặc biệt, không phải vì dữ liệu đó là text hay có thể đọc bằng GET để lấy danh sách member.

**12. Trong Redis Cluster, có thể tùy ý PFMERGE nhiều key ở các slot khác nhau không?**

Không. Các lệnh đa key cần tuân thủ ràng buộc slot; hash tag có thể giúp co-locate các key cần merge, với đánh đổi phân tán tải.

**13. Tại sao vẫn cần TTL khi mỗi HLL chỉ khoảng 12 KiB?**

Vì số HLL key có thể tăng rất lớn theo site, ngày và chiều phân tích; retention còn quyết định có đủ dữ liệu để tính báo cáo hay không.

**14. Có nên dùng HLL để tính số suất đăng ký còn lại chính xác?**

Không. HLL có sai số và không kiểm tra được phần tử cụ thể. Giới hạn nghiệp vụ chính xác cần mô hình và thao tác atomic phù hợp.

**15. Có cần cùng serializer/visitorId giữa các ứng dụng không?**

Có, nếu các ứng dụng cùng ghi hoặc cần hợp HLL của cùng thực thể. Khác biệt bytes đầu vào sẽ làm Redis xem đó như giá trị khác nhau.

## Ghi nhớ

~~~text
SỐ LƯỢT SỰ KIỆN
    INCR counter

SỐ PHẦN TỬ PHÂN BIỆT CHÍNH XÁC
    Redis Set: SADD -> SCARD
    Có member, có thể kiểm tra/xóa/liệt kê

SỐ PHẦN TỬ PHÂN BIỆT GẦN ĐÚNG
    Redis HyperLogLog:
      PFADD key element...   -> cập nhật trạng thái thống kê
      PFCOUNT key           -> ước lượng một tập
      PFCOUNT key1 key2     -> ước lượng hợp hai tập
      PFMERGE dest sources  -> lưu sketch hợp

SPRING DATA REDIS
    StringRedisTemplate.opsForHyperLogLog()
      .add(key, values...)
      .size(keys...)
      .union(destination, sourceKeys...)
      .delete(key)

NHỚ RẰNG
    - Sai số thống kê (~0,81% standard error)
    - Bộ nhớ nhỏ, khoảng 12 KiB cho HLL dense
    - Không membership, không liệt kê, không xóa một ID
    - Đừng cộng DAU để ra MAU
    - TTL theo Redis key; retention phải đủ cửa sổ báo cáo
    - Merge có side effect với destination
    - Hợp nhiều key trong Cluster cần lưu ý hash slot
~~~

**HyperLogLog là lựa chọn thực dụng khi Spring Data Redis cần thống kê số phần tử phân biệt trên tập dữ liệu lớn mà chấp nhận được sai số nhỏ.** Hãy dùng nó để trả lời câu hỏi **“khoảng bao nhiêu?”** và sử dụng Set hoặc nguồn dữ liệu chính xác khác khi hệ thống cần trả lời **“chính xác bao nhiêu, gồm những ai, và phải xử lý từng ai như thế nào?”**.
