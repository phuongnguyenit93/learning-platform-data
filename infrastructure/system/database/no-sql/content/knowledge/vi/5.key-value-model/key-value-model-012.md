# Thực nghiệm truy cập theo khóa và kiểm chứng cập nhật đồng thời

Trong mô hình cơ sở dữ liệu **khóa–giá trị (key–value)**, thao tác cơ bản là cung cấp một **khóa duy nhất** để đọc, ghi hoặc xóa giá trị tương ứng. Mô hình này rất phù hợp cho cache, phiên đăng nhập, bộ đếm, trạng thái giỏ hàng và dữ liệu được tra cứu theo định danh đã biết.

Tuy nhiên, từ nhận định “đọc theo khóa rất nhanh” đến thiết kế một hệ thống đúng khi hàng trăm request cùng cập nhật một khóa là cả một bước quan trọng. Hai luồng có thể đều đọc giá trị cũ rồi ghi đè kết quả của nhau. Một lần ghi có thể thành công nhưng ứng dụng không nhận được phản hồi. Các phép toán chỉ đúng khi thực hiện tuần tự có thể cho kết quả sai dưới tải đồng thời.

Bài thực hành dùng **Redis** làm môi trường minh họa cụ thể cho NoSQL khóa–giá trị. Redis hỗ trợ chuỗi (string), thao tác theo khóa, các lệnh tăng số nguyên nguyên tử và cơ chế transaction lạc quan \`WATCH/MULTI/EXEC\`. Các nguyên tắc về khóa và cạnh tranh cập nhật áp dụng rộng hơn Redis; cú pháp lệnh và mức bảo đảm cụ thể phụ thuộc sản phẩm.

## 1. Mục tiêu và phạm vi thực nghiệm

Sau bài này, người học có thể:

1. Tạo và truy cập dữ liệu qua khóa bằng \`SET\`, \`GET\`, \`MGET\`, \`EXISTS\`, \`DEL\` và \`TTL\`.
2. Phân biệt truy cập trực tiếp theo khóa với tìm kiếm hoặc quét theo điều kiện.
3. Quan sát ảnh hưởng của kích thước giá trị và số lượt gọi mạng tới độ trễ thao tác.
4. **Tái hiện lost update có chủ đích** khi hai tác vụ cùng thực hiện \`GET → tính toán → SET\`.
5. Kiểm chứng \`INCR\`/ \`INCRBY\` giải quyết trường hợp tăng bộ đếm trên một khóa.
6. Dùng \`WATCH/MULTI/EXEC\` để kiểm soát cập nhật kiểu *read–modify–write* phức tạp hơn.
7. Diễn giải những giới hạn của phép thử: tính nguyên tử từng lệnh khác với transaction đa khóa, tính bền vững, tính nhất quán qua replica và tính idempotent của toàn nghiệp vụ.

### Bài toán xuyên suốt

Một cửa hàng có sản phẩm \`P101\`. Ta cần lưu:

| Khóa | Giá trị mẫu | Tác vụ |
| --- | --- | --- |
| \`lab:row84:product:P101\` | \`"Tai nghe Bluetooth"\` | Lấy tên sản phẩm theo ID |
| \`lab:row84:stock:P101\` | \`20\` | Xem và điều chỉnh tồn kho |
| \`lab:row84:views:P101\` | \`0\` | Tăng lượt xem khi nhiều người truy cập |
| \`lab:row84:session:U42\` | \`"active"\` | Lưu giá trị có thời hạn |

Trong key–value store, \`P101\` **không tự động là khóa duy nhất ở mọi loại dữ liệu**. Ta dùng tiền tố như \`product:\`, \`stock:\`, \`views:\` để phân biệt ý nghĩa. Redis cũng không tự suy ra quan hệ giữa các khóa trên chỉ vì chúng có cùng hậu tố.

## 2. Chuẩn bị môi trường

### 2.1. Chạy Redis cục bộ

Yêu cầu:

- Docker có thể chạy container Redis.
- Python 3.10+ và \`pip\` để thực hành đồng thời bằng nhiều luồng.
- Một terminal có thể chạy các lệnh \`docker\`.

Khởi động Redis trong container, chỉ xuất cổng ra loopback của máy đang chạy:

~~~bash
docker run --rm --name kv-row84 -p 127.0.0.1:6380:6379 redis:7-alpine
~~~

Lệnh này chiếm terminal để hiển thị log Redis. Mở **terminal thứ hai** và kiểm tra:

~~~bash
docker exec kv-row84 redis-cli PING
~~~

Kết quả mong đợi:

~~~text
PONG
~~~

Nếu cổng 6380 đã được dùng, chọn một cổng host khác, rồi thay số cổng trong các chương trình Python bên dưới. Nếu Docker yêu cầu tải image, cần kết nối mạng khi chuẩn bị môi trường. Các lệnh trong bài chỉ thao tác với khóa bắt đầu bằng \`lab:row84:\` để tránh thay đổi dữ liệu không liên quan.

Sau khi thực hành, có thể dừng container bằng \`Ctrl+C\` ở terminal chạy Redis hoặc:

~~~bash
docker stop kv-row84
~~~

Vì dùng \`--rm\` và không gắn volume, dữ liệu thử nghiệm mất khi container dừng. Đây là đặc tính của **môi trường thử nghiệm được cấu hình như trên**, không phải kết luận rằng mọi triển khai Redis đều không bền vững.

### 2.2. Cài thư viện Python

~~~bash
python -m pip install "redis>=5,<7"
~~~

Tất cả đoạn Python dưới đây kết nối tới:

~~~python
import redis

r = redis.Redis(
    host="127.0.0.1",
    port=6380,
    db=0,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
)

print(r.ping())  # True nếu kết nối thành công
~~~

\`decode_responses=True\` giúp các giá trị chuỗi được đọc thành \`str\` trong Python. Khi làm việc với dữ liệu nhị phân, nên dùng cấu hình và kiểu dữ liệu tương ứng.

## 3. Thực nghiệm 1: thao tác truy cập trực tiếp theo khóa

### 3.1. Ghi và đọc một giá trị

Chạy trong terminal bằng \`redis-cli\`:

~~~bash
docker exec kv-row84 redis-cli SET lab:row84:product:P101 "Tai nghe Bluetooth"
docker exec kv-row84 redis-cli GET lab:row84:product:P101
docker exec kv-row84 redis-cli EXISTS lab:row84:product:P101
docker exec kv-row84 redis-cli GET lab:row84:product:P999
~~~

Kết quả tương ứng thường là:

~~~text
OK
Tai nghe Bluetooth
1
(nil)
~~~

Trong đó:

- \`SET key value\`: tạo hoặc thay thế giá trị string của khóa.
- \`GET key\`: lấy giá trị theo **chính xác khóa**.
- \`EXISTS key\`: trả về \`1\` nếu khóa tồn tại, \`0\` nếu không.
- \`GET\` khóa không tồn tại trả về \`nil\`.

Mô hình truy cập:

~~~mermaid
flowchart LR
    A["Client biết productId=P101"] --> B["Tạo key: lab:row84:product:P101"]
    B --> C["GET(key)"]
    C --> D["Redis tra khóa"]
    D --> E["Trả giá trị: Tai nghe Bluetooth"]
~~~

Điểm mạnh của key–value là ứng dụng **không cần truy vấn từng bản ghi để tìm ra khóa** khi đã biết định danh. Với cấu trúc băm trong bộ nhớ, thao tác tra khóa trong Redis thường có độ phức tạp trung bình O(1), nhưng độ trễ thực tế vẫn chịu ảnh hưởng của mạng, CPU, kích thước giá trị, bộ nhớ và tải đồng thời.

### 3.2. Ghi đè và xóa

~~~bash
docker exec kv-row84 redis-cli SET lab:row84:product:P101 "Tai nghe khong day"
docker exec kv-row84 redis-cli GET lab:row84:product:P101
docker exec kv-row84 redis-cli DEL lab:row84:product:P101
docker exec kv-row84 redis-cli EXISTS lab:row84:product:P101
~~~

Giá trị sau \`SET\` thứ hai là nội dung mới; \`DEL\` xóa khóa, và \`EXISTS\` trả \`0\`. Nếu mục tiêu chỉ là ghi khi khóa chưa tồn tại, \`SET\` thông thường chưa đủ vì nó **thay thế không điều kiện**.

Thử tạo một lần:

~~~bash
docker exec kv-row84 redis-cli SET lab:row84:product:P101 "Gia tri dau tien" NX
docker exec kv-row84 redis-cli SET lab:row84:product:P101 "Gia tri thu hai" NX
docker exec kv-row84 redis-cli GET lab:row84:product:P101
~~~

\`NX\` nghĩa là chỉ đặt giá trị nếu khóa **chưa tồn tại**. Lần đầu trả \`OK\`; lần thứ hai không thay đổi khóa và Redis CLI hiển thị \`(nil)\`. Giá trị cuối vẫn là \`Gia tri dau tien\`.

### 3.3. Đọc nhiều khóa: nhiều round trip và \`MGET\`

~~~bash
docker exec kv-row84 redis-cli MSET lab:row84:product:P101 "Tai nghe" lab:row84:product:P205 "Cap sac" lab:row84:product:P300 "Chuot"
docker exec kv-row84 redis-cli MGET lab:row84:product:P101 lab:row84:product:P205 lab:row84:product:P300
~~~

\`MSET\` đặt nhiều chuỗi và \`MGET\` đọc nhiều khóa string trong một lần gọi. Từ ứng dụng, điều này có thể giảm **số lượt gửi nhận qua mạng** so với gọi \`GET\` nhiều lần liên tiếp. Đổi lại, một batch trả quá nhiều giá trị lớn vẫn có thể tốn băng thông, bộ nhớ và thời gian phản hồi. Không nên suy ra mọi phép \`MGET\` luôn có chi phí nhỏ hơn trong mọi kiến trúc phân tán hoặc client.

### 3.4. Kiểm chứng thời hạn sống (TTL)

~~~bash
docker exec kv-row84 redis-cli SET lab:row84:session:U42 active EX 30
docker exec kv-row84 redis-cli TTL lab:row84:session:U42
docker exec kv-row84 redis-cli GET lab:row84:session:U42
~~~

\`EX 30\` yêu cầu hết hạn sau **30 giây**. \`TTL\` trả về thời gian còn lại tính bằng giây (giá trị giảm khi thời gian trôi qua); sau khi hết hạn, \`GET\` trả \`nil\`.

Các giá trị đặc biệt của \`TTL\`:

| Giá trị | Ý nghĩa |
| --- | --- |
| Số không âm | Thời gian sống còn lại, tính bằng giây |
| \`-1\` | Khóa tồn tại nhưng không có hạn hết |
| \`-2\` | Khóa không tồn tại |

Tính hết hạn phù hợp cho cache hoặc session, nhưng một TTL ngắn không đảm bảo nghiệp vụ dài hạn được lưu bền vững. Ngoài ra, \`SET key value\` thông thường trên khóa đã có TTL có thể xóa TTL cũ; phải dùng tùy chọn tương ứng nếu muốn giữ hạn hết.

### 3.5. Truy cập theo khóa khác truy vấn theo thuộc tính

Trong ví dụ, \`GET lab:row84:product:P101\` biết sẵn khóa nên rất trực tiếp. Nhưng yêu cầu “tìm mọi sản phẩm có giá dưới 500.000” không tự có lời giải chỉ bằng \`GET\`.

Ứng dụng có thể phải:

- Tạo các **khóa chỉ mục phụ** tự quản lý, chẳng hạn theo nhóm giá hoặc danh mục.
- Dùng kiểu dữ liệu Redis khác phù hợp với pattern truy cập.
- Dùng engine tìm kiếm/truy vấn có hỗ trợ lập chỉ mục theo trường nếu nhu cầu cần thiết.

Không nên dùng \`KEYS *\` như một giải pháp tìm kiếm nghiệp vụ trong môi trường đang tải nặng: lệnh duyệt toàn bộ keyspace có thể chặn thời gian xử lý. \`SCAN\` cho phép duyệt tăng dần nhưng **không thay thế chỉ mục nghiệp vụ**, không bảo đảm thứ tự, có thể thấy bản ghi lặp và cần lặp cho tới khi cursor quay về 0.

## 4. Thực nghiệm 2: đo độ trễ truy cập theo khóa

Độ trễ của lệnh truy cập theo khóa không chỉ phụ thuộc phép tra cứu trong Redis. Mỗi thao tác từ Python còn bao gồm đóng gói request, gửi qua TCP, Redis thực thi, gửi phản hồi và client giải mã.

Thử nghiệm dưới đây đo:

- \`GET\` chuỗi nhỏ so với chuỗi lớn.
- \`SET\` chuỗi nhỏ so với chuỗi lớn.
- Thời gian **end-to-end phía client**, đo riêng từng lần gọi không pipeline.

Tạo file \`latency_lab.py\` trong thư mục thực hành bất kỳ:

~~~python
from math import ceil
from statistics import mean, median
from time import perf_counter_ns
from redis import Redis

r = Redis(host="127.0.0.1", port=6380, decode_responses=False)
PREFIX = "lab:row84:bench:"


def percentile(values, p):
    ordered = sorted(values)
    index = max(0, ceil(p / 100 * len(ordered)) - 1)
    return ordered[index]


def measure(label, action, samples=400):
    # Làm nóng kết nối, tránh tính lần kết nối đầu vào mẫu.
    for _ in range(20):
        action()

    times_ms = []
    for _ in range(samples):
        start = perf_counter_ns()
        action()
        elapsed_ms = (perf_counter_ns() - start) / 1_000_000
        times_ms.append(elapsed_ms)

    print(
        f"{label:17} "
        f"mean={mean(times_ms):7.3f} ms "
        f"p50={median(times_ms):7.3f} ms "
        f"p95={percentile(times_ms, 95):7.3f} ms "
        f"p99={percentile(times_ms, 99):7.3f} ms"
    )


payloads = {
    "128B": b"x" * 128,
    "32KiB": b"x" * (32 * 1024),
}

for size_label, value in payloads.items():
    key = PREFIX + size_label
    r.set(key, value)
    measure(f"GET {size_label}", lambda: r.get(key))
    measure(f"SET {size_label}", lambda: r.set(key, value))

for size_label in payloads:
    r.delete(PREFIX + size_label)
~~~

Chạy:

~~~bash
python latency_lab.py
~~~

Chương trình **in số đo thực tế của môi trường chạy**, không có bảng số cố định cần phải khớp. Các cột có nghĩa:

| Chỉ số | Cách hiểu |
| --- | --- |
| \`mean\` | Độ trễ trung bình của các lần gọi |
| \`p50\` | Trung vị; khoảng 50% thao tác không chậm hơn mức này |
| \`p95\` | Khoảng 95% thao tác không chậm hơn mức này |
| \`p99\` | Cho thấy phần đuôi chậm, nhạy với hiện tượng giật tải |

**Giới hạn của phép đo:** chạy trên loopback, một client và các giá trị nhỏ không mô phỏng được mạng giữa nhiều máy, shard, replica, eviction, cache miss ở tầng ứng dụng hoặc mức tranh chấp thực tế. Không dùng số đo này để khẳng định Redis hay mọi key–value store sẽ đạt latency tương tự ở production.

Để có dữ liệu đáng tin hơn, phải thử đồng thời ở các mức QPS, cấu hình kết nối, kích thước payload, phân bố khóa và thời gian chạy đủ dài; theo dõi cả CPU, memory, network, lỗi và tỷ lệ timeout.

## 5. Bản chất của lost update khi hai client cùng sửa một khóa

Giả sử \`lab:row84:views:P101 = 0\`. Hai request đều muốn tăng lượt xem thêm 1.

Đoạn logic tưởng như đúng:

~~~python
old = int(r.get("lab:row84:views:P101"))
new = old + 1
r.set("lab:row84:views:P101", new)
~~~

Nếu chỉ chạy một luồng, kết quả là 1. Nhưng hai luồng có thể xen kẽ:

| Thời điểm | Client A | Client B | Giá trị trong Redis |
| --- | --- | --- | --- |
| T0 | — | — | 0 |
| T1 | GET → 0 | — | 0 |
| T2 | — | GET → 0 | 0 |
| T3 | Tính 0 + 1 | Tính 0 + 1 | 0 |
| T4 | SET 1 | — | 1 |
| T5 | — | SET 1 | **1** |

Kỳ vọng sau hai lần tăng là **2**, thực tế chỉ **1**. Một lượt tăng bị mất (*lost update*).

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant R as Redis
    participant B as Client B
    A->>R: GET views:P101
    R-->>A: 0
    B->>R: GET views:P101
    R-->>B: 0
    A->>R: SET views:P101 1
    R-->>A: OK
    B->>R: SET views:P101 1
    R-->>B: OK
    Note over A,B: Cả hai nhận OK, kết quả cuối = 1
~~~

Mỗi lệnh \`GET\` hoặc \`SET\` riêng lẻ được Redis thực thi nguyên tử theo ngữ nghĩa của lệnh, nhưng **chuỗi lệnh do ứng dụng ghép lại không mặc nhiên nguyên tử**. Đây là nguồn gây nhầm lẫn phổ biến nhất khi học cập nhật đồng thời.

## 6. Thực nghiệm 3: cố tình tái hiện lost update

Để kết quả tái lập được, dùng \`threading.Barrier\` để buộc **hai worker đọc xong giá trị cũ trước khi bất kỳ worker nào ghi**.

Tạo \`race_lab.py\`:

~~~python
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from redis import Redis

r = Redis(host="127.0.0.1", port=6380, decode_responses=True)
KEY = "lab:row84:views:P101"
r.set(KEY, 0)

barrier = Barrier(2)


def unsafe_increment(worker_id):
    old = int(r.get(KEY))
    print(f"worker={worker_id}: read={old}")

    # Cả hai worker phải tới đây mới được tiếp tục.
    barrier.wait(timeout=10)

    r.set(KEY, old + 1)
    print(f"worker={worker_id}: wrote={old + 1}")


with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(unsafe_increment, [1, 2]))

actual = int(r.get(KEY))
print("Expected:", 2)
print("Actual:  ", actual)
~~~

Chạy:

~~~bash
python race_lab.py
~~~

Một kết quả dự kiến:

~~~text
worker=1: read=0
worker=2: read=0
worker=2: wrote=1
worker=1: wrote=1
Expected: 2
Actual:   1
~~~

Thứ tự in của hai worker có thể khác nhau, nhưng do barrier ép cả hai cùng đọc 0, kết quả cuối **1** là điều bài thực nghiệm chủ đích tái hiện, nếu cả hai thao tác hoàn tất bình thường.

Nếu chương trình gặp \`BrokenBarrierError\`, \`TimeoutError\` hoặc lỗi kết nối, không diễn giải đó là kết quả lost update; cần kiểm tra Redis đang chạy và hai worker có được khởi tạo không.

### Vì sao không dùng \`sleep\` để tạo race?

Một đoạn \`time.sleep(0.1)\` có thể làm khả năng xen kẽ cao hơn, nhưng kết quả phụ thuộc tốc độ CPU, lịch chạy luồng và thời gian mạng. \`Barrier\` mô tả **điều kiện đồng bộ cụ thể**: không luồng nào được ghi cho đến khi cả hai đã đọc. Phép thử vì vậy dễ quan sát hơn.

Kết quả này không phải do Python có Global Interpreter Lock (GIL) mà là do các thao tác tới Redis nằm ở **nhiều lượt gọi độc lập**. Hai tiến trình Java, Go hoặc nhiều API server cũng có thể gặp lỗi tương tự.

## 7. Thực nghiệm 4: tăng bộ đếm bằng lệnh nguyên tử

Redis hỗ trợ \`INCR key\` để tăng giá trị số nguyên đang lưu tại một khóa lên 1, và \`INCRBY key delta\` để cộng một số nguyên khác.

~~~bash
docker exec kv-row84 redis-cli SET lab:row84:views:P101 0
docker exec kv-row84 redis-cli INCR lab:row84:views:P101
docker exec kv-row84 redis-cli INCRBY lab:row84:views:P101 5
docker exec kv-row84 redis-cli GET lab:row84:views:P101
~~~

Giá trị sau \`INCR\` là 1; sau \`INCRBY ... 5\` là **6**. Mỗi lệnh tăng đơn lẻ là một thao tác nguyên tử tại Redis server. Không có khoảng trống \`GET → tính → SET\` do client tự điều phối.

### 7.1. Kiểm chứng dưới nhiều luồng

Tạo \`atomic_counter_lab.py\`:

~~~python
from concurrent.futures import ThreadPoolExecutor
from redis import Redis

r = Redis(host="127.0.0.1", port=6380, decode_responses=True)
KEY = "lab:row84:atomic:counter"
WORKERS = 8
INCREMENTS_PER_WORKER = 1000
EXPECTED = WORKERS * INCREMENTS_PER_WORKER

r.set(KEY, 0)


def work(worker_id):
    for _ in range(INCREMENTS_PER_WORKER):
        r.incr(KEY)
    return worker_id


with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    list(pool.map(work, range(WORKERS)))

actual = int(r.get(KEY))
print(f"Expected: {EXPECTED}")
print(f"Actual:   {actual}")
print(f"Correct:  {actual == EXPECTED}")
~~~

Chạy:

~~~bash
python atomic_counter_lab.py
~~~

Nếu 8 luồng thực hiện đủ 1.000 lần tăng, kỳ vọng:

~~~text
Expected: 8000
Actual:   8000
Correct:  True
~~~

\`INCR\` phù hợp khi **toàn bộ biến đổi là cộng một số vào giá trị của một khóa**. Nhưng nếu một nghiệp vụ yêu cầu “kiểm tra tồn kho còn đủ, giảm tồn kho, đồng thời tạo đơn và lưu lịch sử thanh toán”, chỉ một \`DECR\` không giải quyết đầy đủ các điều kiện và tác động liên quan.

### 7.2. Cập nhật số nguyên và tính idempotent là hai bài toán khác nhau

Giả sử request tăng lượt xem bị timeout, client thử lại:

~~~text
INCR views:P101     -> Redis đã tăng từ 10 lên 11
Phản hồi bị mất
INCR views:P101     -> Redis tăng tiếp từ 11 lên 12
~~~

Hai lệnh \`INCR\` đều **nguyên tử**, nhưng cùng một sự kiện người dùng có thể bị đếm hai lần nếu retry không được nhận diện. Muốn mỗi sự kiện chỉ đếm một lần còn cần **event/request ID**, dấu vết chống lặp và cách gắn việc đánh dấu đã xử lý với thao tác tăng. Tính nguyên tử bảo vệ khỏi **lost update**; cơ chế idempotency bảo vệ khỏi **duplicate execution**.

## 8. Thực nghiệm 5: cập nhật có điều kiện bằng WATCH/MULTI/EXEC

\`INCR\` xử lý tốt phép cộng đơn giản. Nhưng một tác vụ có thể cần **đọc giá trị, kiểm tra điều kiện, tính giá trị mới rồi mới quyết định ghi**. Ví dụ, không cho giảm tồn kho xuống số âm.

Redis cung cấp giao dịch lạc quan:

- \`WATCH key\`: theo dõi sự thay đổi của khóa trước khi giao dịch.
- \`MULTI\`: bắt đầu xếp hàng các lệnh sẽ thực thi trong transaction.
- \`EXEC\`: thực thi các lệnh đã xếp hàng nếu các khóa được watch không bị thay đổi theo điều kiện của Redis; nếu có thay đổi xung đột, transaction bị hủy.
- \`UNWATCH\`: bỏ theo dõi nếu thoát sớm.

### 8.1. Tại sao MULTI/EXEC một mình chưa giải quyết mọi race?

Xét logic:

~~~text
GET stock:P101         -> 1
IF stock > 0:
    MULTI
    SET stock:P101 0
    EXEC
~~~

Hai client có thể cùng đọc 1, đều thấy còn hàng và đều cho phép mua. \`MULTI/EXEC\` chỉ gom những lệnh đã được xếp vào giao dịch; nó **không tự phát hiện thay đổi đã xảy ra từ lúc client đọc dữ liệu trước đó**.

Muốn kiểm tra điều kiện dựa trên trạng thái đã đọc, cần cơ chế như \`WATCH\` trước \`GET\`, hoặc một script/lệnh nguyên tử thực hiện trọn vẹn logic.

### 8.2. Ví dụ mua một sản phẩm bằng optimistic locking

Tạo \`cas_stock_lab.py\`:

~~~python
from concurrent.futures import ThreadPoolExecutor
from redis import Redis, WatchError

r = Redis(host="127.0.0.1", port=6380, decode_responses=True)
KEY = "lab:row84:stock:P101"
INITIAL_STOCK = 5
BUYERS = 20

r.set(KEY, INITIAL_STOCK)


def buy_one(buyer_id):
    while True:
        try:
            # Mỗi lần thử có pipeline riêng, không dùng chung
            # đối tượng pipeline giữa các luồng.
            with r.pipeline() as pipe:
                pipe.watch(KEY)
                raw = pipe.get(KEY)
                stock = int(raw or 0)

                if stock <= 0:
                    pipe.unwatch()
                    return buyer_id, False

                pipe.multi()
                pipe.set(KEY, stock - 1)
                pipe.execute()
                return buyer_id, True

        except WatchError:
            # Khóa đã bị thay đổi: đọc lại và thử với dữ liệu mới.
            continue


with ThreadPoolExecutor(max_workers=BUYERS) as pool:
    results = list(pool.map(buy_one, range(BUYERS)))

successful = sum(1 for _, success in results if success)
remaining = int(r.get(KEY))

print("Initial stock:", INITIAL_STOCK)
print("Successful:   ", successful)
print("Remaining:    ", remaining)
print("Invariant:    ", successful + remaining == INITIAL_STOCK)
~~~

Chạy:

~~~bash
python cas_stock_lab.py
~~~

Vì khởi tạo **5 sản phẩm** và 20 người mua, kỳ vọng nếu tất cả worker hoàn tất bình thường:

~~~text
Initial stock: 5
Successful:    5
Remaining:     0
Invariant:     True
~~~

Khi một worker ghi thành công làm thay đổi \`stock:P101\`, worker khác đã \`WATCH\` và đọc giá trị cũ sẽ nhận \`WatchError\` lúc \`EXEC\`; ứng dụng quay lại đọc số mới. Nó không được dựa trên kết quả đã đọc trước đó để tiếp tục trừ kho.

Redis client \`redis-py\` dùng \`pipeline\` để triển khai \`WATCH/MULTI/EXEC\` trong cùng kết nối tương ứng. Mỗi worker cần tạo **pipeline riêng** cho quá trình tranh chấp. Nếu dùng pipeline ở chế độ thông thường chỉ để batch lệnh, không được mặc định nó thực hiện đầy đủ kiểm soát xung đột.

### 8.3. Bất biến cần giữ

Gọi:

- \`S0\`: số sản phẩm ban đầu.
- \`N\`: số lần mua thành công.
- \`S1\`: số tồn kho sau tất cả thao tác.

Đối với bài lab chỉ trừ mỗi lần một sản phẩm, không có nhập thêm hoặc trả hàng:

\[
S_0 = N + S_1,\quad S_1 \ge 0
\]

Trong ví dụ, \`S0 = 5\`, \`N = 5\`, \`S1 = 0\`. Nếu sau khi chạy chỉ còn 0 nhưng ứng dụng lại thông báo 8 người mua thành công, nghiệp vụ vẫn sai. **Kiểm chứng cả giá trị lưu trữ và kết quả trả về từ các thao tác**, thay vì chỉ nhìn vào một bộ đếm.

### 8.4. Chi phí dưới tải tranh chấp

\`WATCH\` phù hợp với cập nhật có điều kiện, nhưng khi nhiều client cùng sửa một khóa nóng, các lần \`EXEC\` bị hủy sẽ tăng:

- Số lượt đọc lại và retry tăng.
- Độ trễ đuôi p95/p99 có thể cao hơn.
- Một worker có thể bị xung đột liên tục, dù mỗi lần đều xử lý đúng.

Cần cân nhắc giới hạn retry, backoff hợp lý hoặc thiết kế giảm hot key. Trong môi trường vận hành, việc hết ngân sách retry phải được báo là **chưa thành công**, không được âm thầm trả thành công.

## 9. So sánh ba cách cập nhật cùng một khóa

| Cách | Phần được bảo vệ | Kết quả khi cùng tăng bộ đếm | Chi phí và giới hạn |
| --- | --- | --- | --- |
| \`GET → tính → SET\` | Mỗi lệnh riêng lẻ | Có thể mất lượt tăng | Đơn giản nhưng sai khi nhiều worker tranh chấp |
| \`INCR\` / \`INCRBY\` | Toàn bộ phép tăng số nguyên trong một lệnh | Mỗi lệnh thành công được áp dụng một lần | Rất phù hợp bộ đếm; không diễn đạt mọi điều kiện nghiệp vụ |
| \`WATCH → GET → MULTI → SET → EXEC\` | Phát hiện thay đổi trong khoảng đọc–ghi | Các cập nhật xung đột phải thử lại | Linh hoạt hơn, có chi phí retry khi contention cao |

Khi logic cần kiểm tra và cập nhật nhiều trường/khóa theo một điều kiện, còn có thể cân nhắc **script chạy nguyên tử** hoặc primitive transaction theo hệ quản trị. Không thể suy ra tính nguyên tử đa khóa ở một cluster phân tán chỉ từ mô tả “key–value”.

## 10. Thực nghiệm 6: giao dịch cập nhật có điều kiện bằng script Redis

Một cách khác để giảm số round trip và tránh cạnh tranh trong chuỗi \`WATCH\` là đóng gói logic kiểm tra–cập nhật vào **một Lua script**. Redis chạy script như một thao tác nguyên tử đối với các lệnh liên quan trên Redis server; các client khác không thể xen lệnh vào giữa các bước của script đang chạy.

Đoạn script sau giảm tồn kho một đơn vị nếu còn hàng:

~~~lua
local key = KEYS[1]
local current = tonumber(redis.call("GET", key) or "0")

if current <= 0 then
    return 0
end

redis.call("DECR", key)
return 1
~~~

Có thể chạy từ Python:

~~~python
from concurrent.futures import ThreadPoolExecutor
from redis import Redis

r = Redis(host="127.0.0.1", port=6380, decode_responses=True)
KEY = "lab:row84:stock:script:P101"

script = r.register_script("""
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current <= 0 then
    return 0
end
redis.call('DECR', KEYS[1])
return 1
""")

r.set(KEY, 5)


def buy_one(_):
    return int(script(keys=[KEY])) == 1


with ThreadPoolExecutor(max_workers=20) as pool:
    results = list(pool.map(buy_one, range(20)))

print("Successful:", sum(results))
print("Remaining: ", int(r.get(KEY)))
~~~

Kỳ vọng cũng là **5 người mua thành công, tồn kho 0**.

**So sánh với WATCH:** script có thể giảm retry tại client và lượng request mạng khi thao tác ngắn, nhưng logic dài hoặc tốn tài nguyên chạy bên trong script có thể giữ Redis bận, tác động đến các client khác. Chỉ đặt logic kiểm tra–ghi ngắn gọn trong script; không gọi các dịch vụ bên ngoài từ trong script.

Nếu chạy Redis Cluster, những khóa mà script truy cập phải tuân thủ quy tắc định tuyến và phạm vi nguyên tử của cluster. Trong bài này, script thao tác **một khóa** để giữ nội dung minh bạch.

## 11. Cập nhật đồng thời trên nhiều khóa: giới hạn của bài thực hành

Đặt hàng có thể cần:

~~~text
1. Giảm stock:P101 từ 5 xuống 4.
2. Tạo order:O900.
3. Lưu payment:PAY700 ở trạng thái phù hợp.
4. Gửi sự kiện OrderCreated sang queue.
~~~

Phép \`DECR\` hay script trên **chỉ bảo vệ một phần** nếu order và payment nằm ở các dịch vụ khác nhau. Nếu stock đã trừ nhưng bước tạo order thất bại, nghiệp vụ phải có phương án khôi phục hoặc hoàn trả.

Có thể phân loại ranh giới:

| Ranh giới | Cơ chế có thể cân nhắc | Câu hỏi cần trả lời |
| --- | --- | --- |
| Một key string | \`INCR\`, \`DECR\`, \`SET NX\`, Lua hoặc CAS phù hợp | Lệnh có diễn đạt đủ bất biến không? |
| Một nhóm key trên cùng Redis server | \`MULTI/EXEC\`, \`WATCH\`, Lua nếu phù hợp | Những điều kiện, lỗi và rollback được bảo đảm thế nào? |
| Nhiều shard/partition | Transaction hoặc cơ chế phân tán do sản phẩm hỗ trợ | Giới hạn cross-shard và tính nhất quán là gì? |
| Nhiều dịch vụ/đối tác | Outbox, trạng thái nghiệp vụ, idempotency và đối soát | Làm sao biết tác động đã xảy ra khi một bước timeout? |

Chẳng hạn, dùng \`SET lock:key value NX EX ...\` để giành khóa có thể điều phối một số tác vụ, nhưng **không tự là giao dịch**. Lock có thể hết hạn khi worker còn chạy, và hai worker có thể cùng tạo tác động nếu không có fencing, kiểm tra phiên bản hoặc điều kiện ghi ở nơi nhận. Với cập nhật số nguyên đơn giản, dùng \`INCR\` hoặc cập nhật có điều kiện thường rõ ràng hơn tự xây khóa phân tán.

## 12. Đo ảnh hưởng của số lượt gọi: GET tuần tự và MGET

Các request trong ứng dụng thường cần lấy nhiều thuộc tính liên quan: tên sản phẩm, tồn kho, lượt xem. Với cách đặt khóa ở phần đầu, chúng nằm ở những key riêng biệt.

Tạo \`multi_get_lab.py\`:

~~~python
from time import perf_counter_ns
from redis import Redis

r = Redis(host="127.0.0.1", port=6380, decode_responses=True)
PREFIX = "lab:row84:multi:"
KEYS = [f"{PREFIX}{i}" for i in range(100)]

for i, key in enumerate(KEYS):
    r.set(key, str(i))


def time_ms(action):
    start = perf_counter_ns()
    result = action()
    return (perf_counter_ns() - start) / 1_000_000, result


sequential_ms, values_1 = time_ms(lambda: [r.get(k) for k in KEYS])
multi_ms, values_2 = time_ms(lambda: r.mget(KEYS))

print("Values equal:     ", values_1 == values_2)
print("Sequential GET ms:", round(sequential_ms, 3))
print("MGET ms:          ", round(multi_ms, 3))

r.delete(*KEYS)
~~~

Chạy:

~~~bash
python multi_get_lab.py
~~~

Hai cách phải trả về các giá trị theo **cùng thứ tự danh sách key**; thông thường \`MGET\` giảm số round trip. Tuy nhiên, đây là phép đo một lần, dễ nhiễu; nên lặp lại với nhiều mẫu, warmup và quan sát p95/p99 nếu muốn so sánh hiệu năng nghiêm túc.

Nếu truy vấn thường cần cả ba giá trị cùng lúc, có thể cân nhắc:

- Lưu các thuộc tính liên quan vào **một value** để truy cập bằng một khóa.
- Dùng cấu trúc **hash** phù hợp nếu cần truy cập/cập nhật các trường trong cùng một key.
- Batch/pipeline các lệnh nếu không thể gộp dữ liệu.

Sự lựa chọn ảnh hưởng đến kích thước value, phần dữ liệu cần đọc, phạm vi cập nhật và mức độ cạnh tranh của cùng một khóa. Gộp tất cả vào một key lớn không mặc nhiên là tối ưu.

## 13. Thiết kế thực nghiệm kiểm chứng cập nhật đồng thời một cách có ý nghĩa

Trước khi tự kết luận “đã an toàn khi concurrent”, nên xác định một **bất biến có thể đo được** và một cách gây tranh chấp đủ rõ.

### 13.1. Đặt bất biến trước khi chạy

| Tình huống | Bất biến | Giá trị kiểm tra |
| --- | --- | --- |
| Tăng bộ đếm 8 × 1.000 lần | \`counter cuối = số lệnh tăng thành công\` | 8.000 nếu tất cả hoàn tất |
| Bán 5 sản phẩm cho 20 người | \`số mua thành công + tồn kho cuối = 5\` | Không được âm kho |
| Cập nhật cấu hình có version | Chỉ người giữ version còn hiệu lực được ghi | Không mất bản sửa mới hơn |
| Cùng request bị gửi lại | Một ý định nghiệp vụ chỉ tạo một tác động | Cần idempotency, không chỉ atomic counter |

Một kết quả cuối ngẫu nhiên “đúng” trong một lần chạy **không chứng minh** code không có race. Trong lab, \`Barrier\` tạo một lịch xen kẽ chắc chắn để minh họa lỗi; còn kiểm chứng khi tải thật cần chạy nhiều mức contention, quan sát retry và lỗi.

### 13.2. Các biến cần kiểm soát

- **Khởi tạo khóa:** đặt giá trị ban đầu trước khi spawn worker.
- **Số luồng và số lần gọi:** có con số rõ để tính kết quả mong đợi.
- **Phạm vi khóa:** các worker phải cùng cập nhật **một khóa** nếu mục tiêu là tạo tranh chấp.
- **Đồng bộ bắt đầu:** dùng barrier hoặc bộ điều phối để các worker thực sự có thể cùng chạy.
- **Xử lý lỗi:** không nhầm lỗi kết nối với conflict do concurrent update.
- **Số tác động thành công:** đếm dựa trên kết quả lệnh/trạng thái nghiệp vụ, không chỉ số request đã gửi.
- **Độ trễ:** nếu so sánh hiệu năng, đo cả throughput, latency và tỷ lệ retry thay vì chỉ thời gian tổng.

### 13.3. Những dấu hiệu cho thấy phép thử chưa đủ

| Quan sát | Lý do chưa đủ |
| --- | --- |
| Chạy hai lượt tăng tuần tự đều được 2 | Không có cạnh tranh, chưa kiểm chứng concurrent |
| Chạy 100 luồng nhưng mỗi luồng dùng key khác nhau | Không có hot key, có thể bỏ sót lost update |
| \`SET\` đều trả \`OK\` | Hai lệnh ghi đè vẫn có thể đều thành công |
| Số tồn kho cuối không âm | Có thể vẫn trả thành công cho nhiều đơn vượt mức tồn kho |
| Chạy \`INCR\` được 8.000 | Chứng minh phép tăng nguyên tử trong điều kiện thử, chưa chứng minh retry không bị đếm hai lần |
| Thử thành công với một Redis standalone | Chưa phản ánh replication, failover, cluster hoặc giao dịch qua nhiều dịch vụ |

## 14. Các vấn đề cần lưu ý khi đưa vào ứng dụng

### 14.1. Đặt khóa để tránh xung đột và dễ tìm

Một quy ước gợi ý:

~~~text
<environment>:<service>:<entity>:<id>:<purpose>

dev:shop:product:P101:details
dev:shop:product:P101:stock
dev:shop:product:P101:views
~~~

Key nên có:

- Phạm vi tên rõ ràng để tránh trùng giữa hệ thống.
- ID ổn định, không dựa hoàn toàn vào thuộc tính dễ đổi như tên hiển thị.
- Kích thước và cách mã hóa phù hợp; tránh nhúng dữ liệu nhạy cảm thô trong tên key.
- Chiến lược TTL riêng cho cache, session và dữ liệu cần lưu lâu.

Trong Redis Cluster, các khóa có thể được phân phối theo hash slot. Hash tag như \`{P101}\` có thể dùng để yêu cầu một nhóm khóa nằm cùng slot khi cần thao tác nhiều khóa theo khả năng của Redis Cluster, nhưng có thể tập trung tải vào một slot nóng. Không thêm hash tag chỉ để “trông có cấu trúc”.

### 14.2. Tránh khóa nóng

Nếu mọi lượt xem trên toàn hệ thống đều tăng một khóa chung, một điểm lưu trữ có thể thành nút thắt. Giải pháp phân shard counter có thể giúp phân tán ghi:

~~~text
views:P101:shard:0
views:P101:shard:1
views:P101:shard:2
...
views:P101:shard:N
~~~

Mỗi request chọn shard theo quy tắc phân phối phù hợp, rồi \`INCR\` khóa shard. Lúc đọc tổng lượt xem, phải cộng các shard hoặc đọc một giá trị tổng hợp có độ trễ cho phép.

**Đánh đổi:** ghi phân tán hơn nhưng đọc tổng phức tạp hơn, cần cân nhắc độ mới của dữ liệu, chi phí tổng hợp và hành vi khi shard thêm/bớt. Không phải hệ thống nào cũng cần sharded counter.

### 14.3. Độ bền và replica

Trong thực tế:

- **Atomicity** của lệnh \`INCR\` nói về thao tác cập nhật trên instance đang xử lý, không tự chứng minh mọi thay đổi luôn tồn tại sau mất điện.
- **Persistence** phụ thuộc cấu hình snapshot/AOF hoặc cơ chế của sản phẩm.
- **Replication** có thể không đồng bộ; một replica có thể thấy dữ liệu chậm hơn primary.
- **Failover** có thể đặt ra các giả định khác về dữ liệu mới ghi, khả năng đọc sau ghi và retry.
- **Cluster** có giới hạn riêng về thao tác nhiều khóa, định tuyến và hot slot.

Vì vậy, khi thay Redis lab bằng Redis production, Memcached, DynamoDB hoặc một key–value store khác, phải kiểm tra chính xác **ngữ nghĩa của lệnh, mức nhất quán và cách lưu dữ liệu bền vững**, không suy ra từ một bài thử cục bộ.

### 14.4. Hai cách bảo vệ hai loại lỗi khác nhau

~~~text
Lost update:
  Hai request khác nhau muốn thay đổi cùng giá trị
  -> atomic command / CAS / WATCH / transaction

Duplicate execution:
  Cùng một ý định bị gửi lại sau timeout/retry
  -> idempotency key / business unique ID / trạng thái xử lý
~~~

Một nghiệp vụ quan trọng như trừ tiền có thể cần cả hai: tránh **ghi đè** trong cạnh tranh cập nhật và tránh **lặp giao dịch** khi gửi lại yêu cầu.

## 15. Bài tập tự thực hiện

**Bài 1 — Tra cứu theo khóa.** Tạo 10 khóa sản phẩm \`lab:row84:product:P001\` đến \`P010\`, rồi viết Python đọc từng khóa và đọc một lần bằng \`MGET\`. So sánh số lần gọi Redis, số byte phản hồi và độ trễ phía client.

**Bài 2 — Tái hiện lost update.** Sửa \`race_lab.py\` để có 4 worker. Dùng một barrier 4 bên để chắc chắn tất cả worker cùng đọc giá trị ban đầu trước khi ghi. Nếu mỗi worker tăng 1, hãy giải thích vì sao kết quả có thể là 1 thay vì 4.

**Bài 3 — Chuyển sang nguyên tử.** Thay cặp \`GET/SET\` bằng \`INCR\`. Chạy cùng số worker và số lần tăng. Ghi lại giá trị cuối, thời gian tổng và số ngoại lệ nếu có.

**Bài 4 — Giới hạn tồn kho.** Bắt đầu với 10 sản phẩm, cho 100 worker mua đồng thời. Triển khai hai cách: \`WATCH/MULTI/EXEC\` và Lua script. Đảm bảo không có tồn kho âm và số kết quả thành công không vượt quá 10. Quan sát tỷ lệ retry ở cách dùng \`WATCH\`.

**Bài 5 — Lỗi sau cập nhật.** Giả sử \`INCR\` đã thành công nhưng response bị mất, client retry. Hãy đề xuất cách thiết kế để cùng một sự kiện \`eventId\` không bị đếm hai lần. Chỉ ra vì sao \`INCR\` tự nó chưa đáp ứng yêu cầu này.

**Bài 6 — Thiết kế key cho tải lớn.** Nếu một sản phẩm có hàng trăm nghìn lượt xem/giây, hãy so sánh một counter duy nhất với nhiều counter shard. Xác định tác động đến đường ghi, đường đọc và tính nhất quán của tổng được hiển thị.

## Kết luận

Truy cập theo khóa giúp hệ thống lấy được giá trị khi biết chính xác định danh, thường có đường đi ngắn và dễ dự đoán. Tuy nhiên, **đúng khi đọc/ghi một lần** chưa đồng nghĩa với **đúng khi nhiều client cập nhật đồng thời**.

Qua các thực nghiệm:

- \`GET\`/\`SET\` cho thấy khả năng truy cập trực tiếp theo key; \`MGET\` có thể giảm lượt gọi khi cần nhiều key.
- Chuỗi \`GET → tính → SET\` làm phát sinh **lost update** nếu không có kiểm soát xung đột.
- \`INCR\` giải quyết phép tăng bộ đếm **nguyên tử trên một khóa**.
- \`WATCH/MULTI/EXEC\` cho phép kiểm tra trạng thái đã đọc và thử lại khi khóa thay đổi.
- Lua script ngắn có thể gói phép kiểm tra–cập nhật thành một thao tác nguyên tử trên Redis.
- Những nghiệp vụ kéo dài hoặc liên quan nhiều hệ thống còn cần **định danh yêu cầu, transaction phù hợp, cơ chế khôi phục và đối soát**.

Tiêu chí cuối cùng để chọn cách cập nhật không phải chỉ là tốc độ, mà là **bất biến nghiệp vụ nào phải được giữ đúng ngay cả khi request đến đồng thời, timeout hoặc được thực hiện lại**.
