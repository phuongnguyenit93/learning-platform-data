# Consistent hashing, vùng token và nút ảo trong các hệ sử dụng

Trong cơ sở dữ liệu NoSQL phân tán, dữ liệu thường quá lớn hoặc lưu lượng quá cao để một máy xử lý. Hệ thống phải quyết định: **một khóa dữ liệu thuộc node nào, khi thêm hoặc mất node thì dữ liệu chuyển đi đâu, và client cần liên hệ node nào để đọc/ghi?** Đây là những bài toán thuộc **phân mảnh và định tuyến** (*partitioning and routing*).

**Consistent hashing** là một kỹ thuật ánh xạ khóa và các điểm đại diện cho node vào cùng một không gian hash, thường được hình dung như **vòng tròn token**. Đặc điểm quan trọng là khi membership thay đổi, chỉ **một phần** không gian khóa phải đổi owner, thay vì phần lớn khóa thay đổi vị trí như một số cách chia modulo đơn giản.

Từ kỹ thuật đó phát sinh ba khái niệm cần phân biệt:

- **Consistent hashing:** họ thuật toán ánh xạ khóa sang những node/điểm trên không gian hash sao cho thay đổi topology gây xáo trộn tương đối ít.
- **Token range:** một đoạn của không gian hash mà một node hoặc một tập replica có trách nhiệm phục vụ.
- **Virtual node (vnode):** một node vật lý sở hữu **nhiều token hoặc nhiều đoạn token không liền nhau**, thay vì chỉ một vùng liên tục, nhằm giúp cân bằng tải và chia nhỏ công việc phân phối/di chuyển dữ liệu.

Các khái niệm này đặc biệt hữu ích khi tìm hiểu Apache Cassandra và một số thiết kế kiểu Dynamo. Tuy nhiên, **không phải mọi NoSQL đều sử dụng cùng một vòng consistent hashing**: Redis Cluster tổ chức theo 16.384 hash slot; MongoDB hashed sharding chia hashed shard key thành những chunk; một managed service có thể ẩn thuật toán placement khỏi người dùng.

Bài học đi từ phép hash đơn giản, xây dựng vòng token bằng tay, giải thích vnode và replica placement, rồi nối với Cassandra, Redis, MongoDB, vận hành và các bài tập Java.

## 1. Bài toán: từ partition key đến node chứa dữ liệu

Giả sử bảng đơn hàng có khóa:

~~~text
tenant_id = "T17"
order_id  = "O801"
~~~

Với dữ liệu lớn, ứng dụng có thể muốn lưu các đơn hàng trên nhiều node:

~~~text
                            Clients
                               |
                          API / Driver
                               |
                        Partition key
                               |
                      Routing / placement
                         /     |     \
                        v      v      v
                      Node A Node B Node C
~~~

**Partition key** là đầu vào quyết định vị trí lưu trữ logic. Có những hệ lấy hash của partition key, những hệ dùng khoảng giá trị và có hệ kết hợp nhiều chiến lược.

Một hàm ánh xạ lý tưởng cần:

1. **Deterministic:** cùng một key và cùng topology cho cùng kết quả.
2. **Đủ phân tán:** nếu dữ liệu đầu vào phù hợp, các key không tập trung vào ít node chỉ do hash kém.
3. **Định tuyến được:** client/coordinator tìm được node hoặc replica chịu trách nhiệm.
4. **Chịu thay đổi topology:** thêm, xóa hoặc thay node không buộc dời mọi key.
5. **Tôn trọng failure domain:** dữ liệu có bản sao phải tránh đặt replica cùng rack/AZ theo chính sách.

Consistent hashing chủ yếu giải quyết **ánh xạ và độ ổn định khi membership thay đổi**. Nó không tự giải quyết replication, quorum, hotspot, phân quyền hoặc hiệu năng query.

## 2. Hash key: bước đầu của phân mảnh

Cho một hàm hash:

\[
h(k)\longrightarrow t
\]

trong đó:

- `k`: partition key của một bản ghi hoặc một nhóm bản ghi.
- `h`: hàm hash có tính quyết định.
- `t`: token, một giá trị trong không gian token.

Ví dụ minh họa:

~~~text
Key                  Token (giả lập)
-----------------------------------
"customer:C01"       12
"customer:C02"       67
"customer:C03"       38
"customer:C04"       91
~~~

Các token trên chỉ là **số giả lập** để tính tay, không phải kết quả Murmur3 hoặc thuật toán cụ thể của DBMS.

### Không được nhầm hash với mã hóa

Hash dùng cho phân mảnh **không phải cơ chế bảo mật dữ liệu**. Ví dụ MurmurHash3 dùng cho phân phối là non-cryptographic hash; token không được xem như ID bí mật, chữ ký hoặc bằng chứng quyền truy cập.

### Hash tốt không sửa được partition key sai

Nếu hệ dùng:

~~~text
partition_key = "tenant:VERY_LARGE_TENANT"
~~~

cho mọi event của một tenant khổng lồ, toàn bộ phần dữ liệu ấy vẫn có thể tạo **hot partition** dù hash phân phối các tenant khác rất tốt. Hàm hash phân tán **nhiều khóa**, không tự tách **một khóa duy nhất đang quá nóng**.

## 3. Cách chia modulo đơn giản

Một thiết kế dễ nghĩ đến:

\[
\operatorname{node}(k)=h(k)\bmod N
\]

với `N` là số node.

Giả sử `N=4` và token hash là:

| Hash của key | `h mod 4` | Node |
| ---: | ---: | --- |
| 12 | 0 | Node 0 |
| 13 | 1 | Node 1 |
| 14 | 2 | Node 2 |
| 15 | 3 | Node 3 |
| 16 | 0 | Node 0 |

Cách làm này đơn giản, nhưng khi thêm một node:

\[
\operatorname{node}'(k)=h(k)\bmod 5
\]

thì rất nhiều khóa đổi node dù các node cũ vẫn đang khỏe:

| Hash | `mod 4` | `mod 5` | Owner đổi? |
| ---: | ---: | ---: | --- |
| 12 | 0 | 2 | Có |
| 13 | 1 | 3 | Có |
| 14 | 2 | 4 | Có |
| 15 | 3 | 0 | Có |
| 16 | 0 | 1 | Có |
| 20 | 0 | 0 | Không |

Hậu quả:

- Phải di chuyển hoặc đọc lại nhiều dữ liệu.
- Cache phân tán bị invalidation hàng loạt.
- Routing thay đổi trên phần lớn không gian khóa.
- Quá trình thêm node có thể tạo tải mạng và disk lớn.

**Vấn đề không phải phép modulo luôn sai.** Với số partition logic cố định và một bảng ánh xạ partition → node riêng, ta vẫn có thể tránh remap quá nhiều. Vấn đề là **gắn trực tiếp số node thay đổi vào phép `hash % N` cho từng key**.

## 4. Ý tưởng của consistent hashing

Thay vì chia trực tiếp theo số node hiện tại, ta:

1. Chọn một không gian hash có thứ tự.
2. Xem đầu và cuối không gian nối với nhau thành **vòng**.
3. Đặt các điểm đại diện cho node vào vòng.
4. Hash mỗi partition key thành một **token**.
5. Chọn node đầu tiên gặp khi đi theo một chiều quy ước (ví dụ **chiều tăng token**).

Minh họa với token từ 0 đến 99:

~~~text
                  Token 0 / 99
                       |
             A@10      |       B@35
                 \     |      /
                  \    |     /
                   [  RING  ]
                  /         \
             D@85           C@60

Các token node được sắp: 10, 35, 60, 85.
Sau 99 quay lại 0.
~~~

Ta chọn quy tắc:

> **Một token key thuộc node có token node đầu tiên lớn hơn hoặc bằng token key khi đi theo chiều tăng, quay vòng về đầu nếu cần.**

Một số triển khai định nghĩa khác ở chi tiết biên; trong bài, ta thống nhất khoảng sở hữu là **(token trước, token hiện tại]**.

## 5. Tính tay các vùng token trên vòng

Giả sử:

~~~text
Node A ở token 10
Node B ở token 35
Node C ở token 60
Node D ở token 85

Token universe: 0..99 (minh họa)
~~~

Vùng mà mỗi node chịu trách nhiệm:

| Node | Token node | Khoảng sở hữu | Token nguyên tương ứng |
| --- | ---: | --- | --- |
| A | 10 | (85, 10] — vòng qua 99→0 | 86..99 và 0..10 |
| B | 35 | (10, 35] | 11..35 |
| C | 60 | (35, 60] | 36..60 |
| D | 85 | (60, 85] | 61..85 |

Các khoảng trên **không chồng lấn và phủ toàn bộ không gian token 0..99**. Mỗi token thuộc đúng một owner trong mô hình **một bản sao**.

Ví dụ định tuyến:

~~~text
hash(key-1) =  7  → Node A
hash(key-2) = 24  → Node B
hash(key-3) = 50  → Node C
hash(key-4) = 80  → Node D
hash(key-5) = 96  → Node A
~~~

### Chú ý biên mở và đóng

Theo quy ước **(previous, current]**:

- Token 35 thuộc B, không thuộc C.
- Token 36 thuộc C.
- Token 85 thuộc D.
- Token 86 thuộc A.
- Token 10 thuộc A.
- Token 11 thuộc B.

Nếu trong một bài toán bạn đổi thành **[previous, current)**, phải đổi cách chọn owner tương ứng. Sự khác biệt một dấu bằng có thể khiến logic routing sai tại biên.

## 6. Wrap-around: đoạn từ cuối vòng trở về đầu

Trong mô hình số 0..99, Node A giữ:

~~~text
(85, 10] =
  86, 87, ..., 99, 0, 1, ..., 10
~~~

Khoảng này gọi là **wrap-around range** vì qua cuối không gian và trở về đầu.

Một hàm kiểm tra khoảng trong mô hình minh họa:

~~~java
static boolean belongsToRange(
        int token, int previous, int current) {
    if (previous < current) {
        return token > previous && token <= current;
    }
    if (previous > current) {
        // Wrap-around.
        return token > previous || token <= current;
    }
    // previous == current cần quy ước riêng, chẳng hạn
    // một node duy nhất sở hữu toàn vòng.
    throw new IllegalArgumentException(
            "Ambiguous full-ring range");
}
~~~

Không nên viết điều kiện chung:

~~~text
token > previous AND token <= current
~~~

cho mọi khoảng, vì với wrap-around `previous=85` và `current=10`, điều kiện đó luôn sai.

### Không gian token thực không nhất thiết 0..99

Ví dụ số nhỏ giúp tính tay. Cassandra dùng partitioner và miền token lớn; với Murmur3Partitioner phổ biến, token nằm trong không gian số nguyên có dấu 64 bit. Người triển khai phải dùng **logic token ring của DBMS**, không tự lấy modulo 100 hoặc tùy ý biến đổi số token khi thực hiện routing.

## 7. Thêm một node vào vòng: chỉ một vùng đổi owner

Vòng ban đầu:

~~~text
A@10, B@35, C@60, D@85
~~~

Thêm Node E tại token 48:

~~~text
Trước:  (35,60] thuộc Node C.
Sau:    (35,48] thuộc Node E.
        (48,60] thuộc Node C.
~~~

Bảng ví dụ:

| Token key | Owner trước | Owner sau | Có đổi? |
| ---: | --- | --- | --- |
| 12 | B | B | Không |
| 38 | C | E | Có |
| 46 | C | E | Có |
| 48 | C | E | Có |
| 49 | C | C | Không |
| 73 | D | D | Không |
| 96 | A | A | Không |

**Chỉ các key trong khoảng (35,48]** thay owner trong mô hình một bản sao của vòng minh họa.

Đây là điểm khác biệt quan trọng so với `hash % N`: membership thay đổi nhưng phần lớn key giữ nguyên owner.

### Thêm node không có nghĩa dữ liệu tự xuất hiện trên node mới

Placement metadata có thể xác định rằng E phải sở hữu khoảng (35,48], nhưng **dữ liệu cũ của khoảng đó vẫn phải được chuyển** từ nơi phù hợp sang E bằng bootstrap/streaming, tùy hệ.

Chúng ta cần phân biệt:

~~~text
1. Bản đồ owner mới được tính.
2. Dữ liệu thực đã chuyển tới E.
3. E đủ điều kiện phục vụ theo consistency/repair policy.
~~~

Không đánh dấu bước 1 là “migration hoàn tất”.

## 8. Xóa node hoặc node hỏng: vùng nào đổi owner?

Tiếp tục vòng sau khi thêm E:

~~~text
A@10, B@35, E@48, C@60, D@85
~~~

Nếu Node C bị loại khỏi vòng:

~~~text
Trước: (48,60] thuộc C.
Sau:   (48,85] thuộc D.
~~~

D trở thành owner chính của vùng cũ C trong mô hình một bản sao. Những vùng khác không nhất thiết thay đổi.

### Xóa node có kế hoạch khác node đột ngột hỏng

- **Decommission có kế hoạch:** DBMS có thể stream dữ liệu, cập nhật topology và đợi những mốc an toàn.
- **Node crash:** metadata/tập replica có thể chưa đổi ngay; các node khác có thể **phục vụ bản sao** theo RF và consistency level, hoặc chờ thay node.
- **Thay node:** cần xây lại replica bằng streaming/repair để đạt redundancy cũ.

Không nên hiểu ví dụ “xóa C thì D nhận vùng” như một mô tả đủ của Cassandra production. Với RF lớn hơn một, **nhiều node tham gia vai trò replica** và chiến lược chống lỗi có thể tạo thay đổi placement phức tạp hơn.

## 9. Consistent hashing giảm remapping đến mức nào?

Trong mô hình hash cân bằng với các vị trí node phân bố ngẫu nhiên và đồng đều, khi thêm node thứ `N+1`, tỉ lệ không gian khóa mà node mới nhận có kỳ vọng xấp xỉ:

\[
\frac{1}{N+1}
\]

Ví dụ thêm node thứ 5 vào hệ có 4 node đồng đều:

\[
\mathbb E[\text{share of new node}]\approx \frac{1}{5}=20\%
\]

**Đây là kỳ vọng dưới mô hình ngẫu nhiên, không phải định luật mỗi lần thêm node chính xác 20% key.** Nếu một node có một token đặt gần node trước, nó có thể nhận một vùng rất nhỏ; nếu rơi sau một khoảng token lớn, nó có thể nhận một vùng rất lớn.

### Nhiều replica làm việc di chuyển phức tạp hơn

Khi RF=3, thay đổi vòng có thể làm thay đổi:

- Primary/preferred owner của một token range.
- Tập ba replica theo replication strategy.
- Dữ liệu cần stream để những replica mới đủ bản sao.
- Request routing, coordinator preference và repair coverage.

Vì vậy **tỉ lệ key đổi owner chính** không phải lúc nào cũng bằng **tỉ lệ byte truyền qua mạng** trong thao tác bootstrap thực tế.

## 10. Điểm yếu của một token cho mỗi node

Nếu bốn node có token:

~~~text
A@10, B@35, C@60, D@85
~~~

thì độ dài các vùng:

~~~text
A: 25 token (86..99 và 0..10)
B: 25 token
C: 25 token
D: 25 token
~~~

Vòng này cân bằng đẹp vì token được cố ý đặt đều.

Nhưng thử:

~~~text
A@10, B@12, C@70, D@85
~~~

Khi đó:

~~~text
A: (85,10] → 25 token
B: (10,12] →  2 token
C: (12,70] → 58 token
D: (70,85] → 15 token
~~~

C có thể sở hữu phần lớn không gian hash, trong khi B gần như không có. **Một token ngẫu nhiên mỗi node có độ lệch tải cao** khi số node còn ít hoặc phân bố token không đều.

Nếu mỗi node có một token được cân thủ công, việc thêm/xóa node cần chọn token cẩn thận và có thể tạo nhiều công đoạn rebalance.

**Virtual nodes** là một kỹ thuật giúp phân phối những vùng nhỏ trên nhiều node vật lý.

## 11. Virtual node (vnode) là gì?

**Vnode** là một đơn vị sở hữu token/range logic; một node vật lý có thể được gán nhiều token khác nhau trên vòng.

Ví dụ:

~~~text
Node vật lý A có token: 10, 50
Node vật lý B có token: 25, 65
Node vật lý C có token: 40, 80
~~~

Thứ tự token:

~~~text
10(A) → 25(B) → 40(C) → 50(A) → 65(B) → 80(C) → wrap 10(A)
~~~

Sở hữu:

| Vnode/token hiện tại | Khoảng token giữ | Node vật lý |
| --- | --- | --- |
| A@10 | (80,10] | A |
| B@25 | (10,25] | B |
| C@40 | (25,40] | C |
| A@50 | (40,50] | A |
| B@65 | (50,65] | B |
| C@80 | (65,80] | C |

Lưu ý **A không chỉ giữ một khoảng liên tục**:

~~~text
Node A: (80,10] và (40,50]
Node B: (10,25] và (50,65]
Node C: (25,40] và (65,80]
~~~

Vnode giúp các node có nhiều đoạn rải trên không gian hash, từ đó **cân bằng trung bình** tốt hơn so với mỗi node chỉ có một token ngẫu nhiên.

### Vnode không phải một máy ảo

Tên “virtual node” dễ gây nhầm:

- **Node vật lý/VM:** một instance chạy DBMS.
- **Vnode:** một điểm token hoặc đơn vị sở hữu range logic trong thuật toán placement.

Một máy có thể sở hữu nhiều vnodes nhưng chúng **không độc lập về lỗi host**: host chết thì mọi vnode của host đó đều mất khả năng phục vụ cùng lúc.

## 12. Vnodes giúp cân bằng thế nào?

Giả sử có ba node vật lý, mỗi node được gán nhiều điểm token đủ rải đều.

~~~text
Một token/node:
  Node A giữ một đoạn lớn.
  Node B giữ một đoạn nhỏ.
  Node C giữ phần còn lại.

Nhiều token/node:
  A giữ các đoạn A1, A2, A3, ...
  B giữ các đoạn B1, B2, B3, ...
  C giữ các đoạn C1, C2, C3, ...
~~~

Khi mỗi node nhận nhiều vùng từ nhiều vị trí, tổng độ dài các vùng của node có xu hướng ít biến động hơn.

### Cân bằng token space không chắc cân bằng disk bytes

Phân phối đều không gian hash chỉ giúp nếu **khóa/partition và kích thước dữ liệu** tương đối phù hợp với giả định:

~~~text
Range X: 10 triệu record nhỏ
Range Y: 1 partition khổng lồ
~~~

Hai range có thể dài bằng nhau trên vòng nhưng chiếm dung lượng khác nhau rất lớn. Tương tự, số byte gần bằng nhau chưa chắc số truy cập/giây gần bằng nhau.

Vnodes cải thiện **granularity của ownership**, nhưng không tự giải quyết:

- Partition size skew.
- Hot tenant hoặc hot product.
- Time-series partition mới nhất quá nóng.
- Một key duy nhất bị nhiều client cập nhật.
- Query có fan-out lớn trên nhiều partition.

Muốn giải quyết hotspot cần xem **partition-key design, bucketing, sharded counters, cache, pre-aggregation hoặc mô hình truy cập**, không chỉ thêm vnodes.

## 13. Vnodes khi thêm node: chia nhỏ dữ liệu lấy từ nhiều nơi

Một node mới trong hệ mỗi node chỉ có một token có thể phải lấy phần lớn dữ liệu từ **một node kế nhiệm**.

Với vnodes:

~~~text
Old nodes: A, B, C
New node:  D

D được cấp các token mới:
  D1 trong một range cũ của A
  D2 trong một range cũ của B
  D3 trong một range cũ của C
~~~

D có thể nhận dữ liệu thuộc nhiều đoạn từ **nhiều source nodes**. Điều này có thể giúp phân tán nguồn streaming và giảm sự phụ thuộc vào chỉ một máy.

### Đánh đổi

Nhiều ranges cũng có nghĩa:

- Nhiều metadata về ownership.
- Nhiều công việc stream/rebuild/repair theo token ranges.
- Nhiều connection và coordination points trong một số operations.
- Quá trình kiểm tra đúng placement có thể phức tạp hơn.

Vì vậy **càng nhiều vnode không phải lúc nào cũng càng tốt**. Số token/node nên theo phiên bản DBMS, công cụ vận hành, mục tiêu cân bằng và tài liệu triển khai cụ thể.

## 14. Weighted placement và node có cấu hình không đồng nhất

Một cụm có thể chứa:

~~~text
Node A: 8 TB usable
Node B: 8 TB usable
Node C: 16 TB usable
~~~

Nếu phân bố dữ liệu đều **theo node** thì C có thể chưa được tận dụng tương xứng. Một hướng là sử dụng **trọng số/ownership mục tiêu** để node mạnh nhận nhiều token ranges hơn.

Ví dụ mong muốn:

~~~text
A: 25% ownership
B: 25% ownership
C: 50% ownership
~~~

Tuy nhiên, **không phải cứ cấu hình gấp đôi token/vnode là Cassandra tự động có cơ chế trọng số đơn giản trên mọi phiên bản**. Cách cấp token, thuật toán allocation và khuyến nghị cho node không đồng cấu hình phụ thuộc hệ. Một cluster Cassandra thường được vận hành với giả định và tooling có giới hạn riêng; phải tham khảo chính xác topology/version.

Nếu các node khác biệt lớn về disk, CPU hoặc network, cần tính cân bằng theo **nút thắt nhỏ nhất**, không chỉ dung lượng.

## 15. Vnode count là tham số cần chọn có chủ đích

Các tài liệu lịch sử Cassandra thường nhắc số lượng vnodes mặc định theo thời kỳ, nhưng **không nên thuộc một số cố định và áp cho mọi Cassandra version hoặc managed Cassandra service**.

Khi chọn số token/node cần cân nhắc:

| Yếu tố | Ít vnode/token node | Nhiều vnode/token node |
| --- | --- | --- |
| Ownership ranges | Ít, đơn giản hơn | Nhiều đoạn nhỏ hơn |
| Cân bằng nếu token được cấp ngẫu nhiên | Có thể lệch đáng kể | Thường ít biến động hơn |
| Thêm node | Ít nguồn/range cần chuyển hơn | Có thể stream từ nhiều nơi |
| Metadata/range management | Thường thấp hơn | Có thể tăng |
| Repair/streaming complexity | Ít range hơn | Nhiều range cần theo dõi |
| Khả năng tối ưu token placement thủ công | Khả thi trong cluster nhỏ | Phức tạp khi nhiều token |

Điểm quyết định không phải “số lớn là tốt”, mà là **tối ưu giữa balance, streaming, repair, cluster size, phiên bản và tooling**.

## 16. Consistent hashing không thay thế replication factor

Đến đây, ví dụ vòng token mới nói về **owner một bản sao**. Hệ sản xuất thường có RF lớn hơn một.

Giả sử:

~~~text
Ring token order:
A@10 → B@35 → C@60 → D@85

RF = 3
~~~

Một sơ đồ đơn giản có thể hình dung **token key được hash**, sau đó chọn nhiều node phù hợp theo quy tắc replication:

~~~text
hash(key)=20
Primary/preferred placement point: B@35
Replica candidates: B, C, D
~~~

Nhưng đây chỉ là **minh họa nguyên lý theo vòng**.

### Replica placement còn phụ thuộc topology

Trong Cassandra với `NetworkTopologyStrategy`, replication cần xét:

- RF của **mỗi datacenter**.
- Rack labels/snitch.
- Các node/token ownership.
- Khả năng phân tán replica qua rack.
- Phạm vi DC mà coordinator đang thao tác.

**Không dùng “đi tiếp đúng RF node liên tiếp trên vòng” làm thuật toán chính xác cho mọi Cassandra cluster**, vì rack-aware placement có thể bỏ qua những candidate cùng rack để đạt anti-affinity.

## 17. Node, rack và datacenter quyết định khả năng chịu lỗi

Ví dụ DC có ba rack:

~~~text
dc_hcm
  rack-a: node-a1, node-a2
  rack-b: node-b1, node-b2
  rack-c: node-c1, node-c2

RF=3
~~~

Một partition có thể được bố trí:

~~~text
Replica P1: node-a1 / rack-a
Replica P2: node-b2 / rack-b
Replica P3: node-c1 / rack-c
~~~

Nếu mất một rack, vẫn còn hai replica. Với một giao thức cần majority=2/3, topology này có khả năng đáp ứng điều kiện về số node còn sống.

Nhưng nếu hai replica P1/P2 cùng rack-a, mất rack-a chỉ còn một bản sao. **Vnodes không biến hai replica trên cùng rack thành hai failure domains độc lập.**

### RF và vnode có vai trò khác nhau

| Thuộc tính | Mục tiêu |
| --- | --- |
| **Token placement** | Gán vùng hash cho các node |
| **Virtual nodes** | Chia quyền sở hữu thành nhiều vùng nhỏ trên một node |
| **Replication factor** | Định số replica dự kiến |
| **Rack/DC awareness** | Tránh lỗi tương quan của các replica |
| **Quorum/consistency level** | Xác định điều kiện đọc/ghi |

Một thiết kế đúng phải kết hợp các yếu tố thay vì thay thế chúng cho nhau.

## 18. Cassandra và Murmur3Partitioner

Trong Apache Cassandra hiện đại, **Murmur3Partitioner** là partitioner phổ biến. Nó hash phần **partition key** thành token, sau đó ring topology và replication strategy quyết định các replica.

Với Murmur3Partitioner, không gian token được biểu diễn qua **giá trị số nguyên có dấu 64 bit** theo ngữ nghĩa của partitioner.

~~~text
partition key
     │
     ▼
Murmur3Partitioner
     │
     ▼
signed 64-bit token
     │
     ▼
Token ring / replica placement
~~~

### Cần hiểu đúng “hash partition key”

Giả sử bảng:

~~~sql
CREATE KEYSPACE shop
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc_hcm': 3
};

CREATE TABLE shop.orders_by_customer (
    tenant_id text,
    customer_id text,
    order_id text,
    placed_at timestamp,
    total_minor bigint,
    PRIMARY KEY ((tenant_id, customer_id), order_id)
);
~~~

Partition key là **cặp `(tenant_id, customer_id)`**, không chỉ `order_id`. Các hàng của một partition có cùng cặp khóa sẽ được đặt theo **cùng token/replica placement**, rồi phân biệt trong partition bằng clustering key `order_id`.

Điều này giúp đọc đơn hàng của một khách theo partition, nhưng nếu một khách có hàng triệu đơn và workload liên tục ghi/đọc vào cùng partition, nó có thể trở thành quá lớn/nóng. **Token ring không tự chia một partition key thành nhiều node**.

### Về độ chính xác của hash

Không nên tự lấy chuỗi hiển thị `tenant_id + ":" + customer_id` rồi dùng một thư viện Murmur3 bất kỳ để đoán token Cassandra. CQL type encoding, serialization của partition key nhiều thành phần, partitioner và version phải đúng; **driver/DBMS chịu trách nhiệm tạo token thực**.

## 19. Cassandra: replication strategy và token ownership

Ví dụ keyspace nhiều DC:

~~~sql
CREATE KEYSPACE orders_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hcm': 3,
    'dc_hn': 3
}
AND durable_writes = true;
~~~

Ý nghĩa:

~~~text
Mỗi partition:
  3 replicas ở dc_hcm
  3 replicas ở dc_hn
~~~

**Token ring và RF kết hợp:** token quyết định phạm vi key, replication strategy xác định node nào trong từng DC thực sự là replica, và Cassandra phối hợp việc nhận ghi/đọc theo consistency level.

### Một partition không được chia theo từng hàng clustering

Nếu:

~~~text
tenant_id=T1, customer_id=C42
  orderId=O1
  orderId=O2
  orderId=O3
~~~

thì ba hàng có cùng partition key và cùng token, không phân bố vòng theo `orderId` riêng. Thay đổi clustering order chỉ ảnh hưởng thứ tự/hình dạng đọc trong partition, **không làm key được hash sang token khác**.

## 20. Cassandra: vnode count và cấu hình token

Cassandra có những cấu hình/cơ chế gán token, ví dụ node có một token hoặc nhiều tokens/vnodes theo chế độ và phiên bản triển khai.

Một mô hình khái niệm:

~~~text
Node A:
  token tA1, tA2, tA3, ...

Node B:
  token tB1, tB2, tB3, ...
~~~

Trong Cassandra, cơ chế token assignment khi bootstrap và các tham số cấu hình như `num_tokens` có thể ảnh hưởng số token node sở hữu. **Giá trị mặc định, mức khuyến nghị và các tính năng cân bằng token thay đổi theo phiên bản/managed service**; không tự áp một giá trị từ tài liệu khác phiên bản.

### Vì sao thay token là thao tác dữ liệu lớn?

Nếu token assignment của node đổi:

- Owner của nhiều token ranges có thể thay đổi.
- Những replica mới cần stream dữ liệu.
- Những replica cũ có thể cần cleanup sau migration.
- Repair và metadata topology cần cập nhật.
- Request routing/driver metadata phải bắt kịp.

Không được đổi danh sách token của node đang phục vụ như một biến UI rồi nghĩ dữ liệu tự di chuyển an toàn.

## 21. Cassandra: coordinator và token-aware routing

Một ứng dụng thường không tự tính node đích từ token rồi mở TCP kết nối đúng replica. **Driver** hoặc **coordinator** đảm nhiệm nhiều bước.

~~~text
Application
     │
     ▼
Cassandra driver
  - partition key routing information
  - token map / replica metadata
  - local DC / load balancing policy
     │
     ▼
Coordinator node
     │
     ├── Replica A
     ├── Replica B
     └── Replica C
~~~

**Token-aware routing** giúp driver chọn coordinator phù hợp/ưu tiên node gần replica cho partition được truy cập, giảm đi lại mạng không cần thiết.

### Không phải request nào cũng token-aware

Driver cần biết **routing key** của query. Những trường hợp như:

- Query không cung cấp đầy đủ partition key.
- Một batch chứa nhiều partition keys.
- Truy vấn phân tích/quét nhiều ranges.
- Một lệnh không có bind values được nhận diện chính xác.

có thể không định tuyến giống query point lookup.

### Prepared statement và bind partition key

Ví dụ CQL:

~~~sql
SELECT order_id, placed_at, total_minor
FROM shop.orders_by_customer
WHERE tenant_id = ?
  AND customer_id = ?;
~~~

Khi driver nhận đủ partition key và metadata cần thiết, nó có thể xác định token/routing key theo cách được hỗ trợ.

Trong ứng dụng Java, dùng prepared/bound statement và cấu hình driver đúng local DC để driver có thể tận dụng token-aware routing. Không hardcode “customer C42 luôn nằm trên node A” vì rebalancing/failover có thể đổi replica.

## 22. LOCAL_QUORUM và vnode: hai chiều khác nhau

Giả sử Cassandra keyspace có RF=3 trong `dc_hcm`.

~~~text
Replica set cho partition P:
  N1 / rack-a
  N4 / rack-b
  N7 / rack-c
~~~

Với `LOCAL_QUORUM`, ngưỡng majority theo số học là:

\[
\left\lfloor \frac{3}{2}\right\rfloor+1=2
\]

Điều này không thay đổi chỉ vì mỗi node có 1, 16 hay nhiều vnode:

- **RF:** một partition cần bao nhiêu replicas trong DC.
- **Vnode count:** mỗi node sở hữu bao nhiêu token ranges nói chung.
- **LOCAL_QUORUM:** số replica cần đáp ứng điều kiện ở DC local cho operation, theo semantics DBMS.

Đừng nhầm **nhiều token của cùng node** thành nhiều ACK độc lập cho một partition. **Một máy chứa 100 vnodes vẫn là một failure domain host**, không thể dùng các vnode đó để thay thế ba replica trên ba node độc lập.

## 23. Token-aware routing khác dữ liệu có nhiều bản sao

Một lập luận sai thường gặp:

> “Nếu client biết token của key, nó chỉ cần gọi đúng một node, không cần coordinator hoặc quorum.”

Token chỉ giúp tìm **vị trí chịu trách nhiệm**. Nếu một thao tác cần:

- Ghi tới nhiều replica.
- Read repair hoặc chọn version.
- LWT/compare-and-set.
- Transaction hoặc commit condition.

thì giao thức vẫn cần phối hợp. Chọn một replica đúng vị trí không tự làm thao tác trở thành strongly consistent.

### Locality không đồng nghĩa freshness

Một node local có thể phản hồi nhanh nhưng đang stale, trong khi replica khác đã nhận write mới. Nếu nghiệp vụ cần đọc mới, hãy chọn consistency/read concern phù hợp thay vì chỉ tối ưu đường mạng.

## 24. Cassandra operations: bootstrap, repair và ownership

Khi thêm node, CQL schema và topology metadata có thể chỉ ra các token ranges mà node mới phải giữ. Nhưng cần **streaming/repair** để dữ liệu thực được chuyển.

Trình tự ý tưởng:

~~~text
1. Node mới tham gia theo quy trình bootstrap.
2. Metadata token/replica map được điều chỉnh.
3. Node mới stream những ranges được giao.
4. Hệ giám sát throughput, disk, compaction, errors.
5. Kiểm tra dữ liệu/replica health và hoàn tất transition.
~~~

Không được coi một node hiển thị `UP` là bằng chứng **mọi token range đã có đủ data và repair xong**.

### Khi decommission hoặc replace

Nếu xóa node có kế hoạch:

- Dữ liệu ranges cũ cần được giữ trên các node đúng topology mới.
- Cần kiểm tra capacity và streaming bandwidth.
- Các node còn lại có thể tăng tải tạm.
- Token-aware driver cần cập nhật topology.

Nếu node hỏng đột ngột:

- Replica khác có thể phục vụ tùy RF/consistency.
- Redundancy giảm cho tới khi replace/repair.
- Không nên xóa metadata tùy tiện rồi tự suy dữ liệu an toàn.

## 25. Vnode và repair: chia nhỏ ownership có chi phí

Khi một node sở hữu nhiều token ranges rải rác, quá trình anti-entropy repair/streaming có thể cần xét nhiều khoảng.

~~~text
Node A:
  Range A1
  Range A2
  Range A3
  ...
~~~

Ưu điểm:

- Nhiều nguồn dữ liệu có thể tham gia streaming.
- Khả năng cân bằng ownership tốt hơn trong nhiều topology.
- Có thể chia nhỏ đơn vị khôi phục theo token range.

Nhược điểm tiềm năng:

- Metadata/số range tasks nhiều hơn.
- Repair có thể phức tạp hơn khi phải theo dõi nhiều range/replica set.
- Quá nhiều job nhỏ có thể tạo overhead.
- Trong cluster lớn, topology changes có thể tác động nhiều tập replica.

Do đó lựa chọn vnode count là **đánh đổi vận hành**, không phải tối đa hóa một chiều.

## 26. Tombstones, TTL và replica offline

Cassandra sử dụng tombstone cho các thao tác xóa/TTL theo cơ chế lưu trữ. Một replica offline có thể bỏ lỡ thông tin xóa:

~~~text
T0: value exists on A,B,C
T1: C offline
T2: DELETE replicated to A,B
T3: C returns with old value
~~~

Hệ cần repair/anti-entropy phù hợp để C nhận thông tin deletion. Nếu tombstone bị dọn quá sớm và replica cũ quay lại, có thể phát sinh rủi ro **resurrection** trong một số tình huống.

Mối liên hệ với bài này:

1. Token ranges quyết định phạm vi dữ liệu node chịu trách nhiệm.
2. RF quyết định những replica cần đồng bộ.
3. Vnodes làm số range cần quản lý tăng.
4. Repair phải tuân thủ topology và retention.

**Không giảm tombstone grace/repair frequency tùy tiện chỉ để giảm disk** khi chưa hiểu ngữ nghĩa của hệ đang chạy.

## 27. Quan sát token ring trong Cassandra

Các lệnh quan sát phổ biến ở môi trường lab/cluster:

~~~bash
nodetool status
nodetool ring
nodetool describecluster
~~~

Mục đích:

- Xác định node nào đang UP/DOWN và thuộc DC nào.
- Quan sát token/ownership theo thông tin công cụ cung cấp.
- Kiểm tra topology có khớp thiết kế không.
- Phát hiện thay đổi membership hoặc phân bố bất thường.

**Cẩn thận:** output có thể dài khi có nhiều vnodes; phần trăm ownership hiển thị cần hiểu cách công cụ tính, đặc biệt khi RF/định nghĩa ownership khác nhau. Không tự suy từ “node A sở hữu 30% tokens” rằng node A chắc chắn có đúng 30% bytes hoặc 30% traffic.

### Các metric nên theo dõi

| Nhóm | Ví dụ tín hiệu |
| --- | --- |
| Token topology | Token ranges, ownership, replica placements |
| Membership | Node UP/DOWN, bootstrap/decommission status |
| Data distribution | Disk usage/node, table sizes, hot partitions |
| Reads | p95/p99 read latency, timeouts, read inconsistencies |
| Writes | p95/p99 write latency, unavailable writes |
| Streaming | Pending/failed streams, throughput |
| Repair | Last successful repair, mismatched ranges |
| Compaction | Backlog, disk free, write amplification |
| Cross-DC | RTT, lag, inter-DC traffic |

### Không sửa topology chỉ vì output “xấu”

Đổi token ownership/RF trên production có thể di chuyển lượng lớn dữ liệu. Cần capacity plan, backup, change window và quy trình do tài liệu của đúng phiên bản DBMS hướng dẫn.

## 28. Redis Cluster: hash slots, không phải vòng vnode Cassandra

**Redis Cluster** là ví dụ quan trọng của một **thiết kế định tuyến phân mảnh khác**.

Redis Cluster tổ chức không gian khóa thành **16.384 hash slots** (từ 0 đến 16.383). Khóa được ánh xạ vào một slot dựa trên CRC16 và phép modulo:

\[
\operatorname{slot}(k)
=\operatorname{CRC16}(k)\bmod 16384
\]

(Có quy tắc đặc biệt cho **hash tags** trong tên key.)

~~~text
Key
 │
 ▼
CRC16/hash tag
 │
 ▼
Hash slot 0..16383
 │
 ▼
Slot ownership map → Redis primary node
 │
 ▼
Optional Redis replicas của primary
~~~

### Điểm tương đồng với consistent hashing

Thêm node **không cần tính lại `hash(key) % số node` cho mọi key**. Thay vào đó, ta **di chuyển quyền sở hữu các slots** từ các node hiện tại sang node mới.

### Điểm khác

- Redis Cluster dùng **không gian slot có kích thước cố định** và bảng slot → node.
- Không nên mô tả Redis Cluster như mỗi Redis node sở hữu các token vnode ngẫu nhiên trên vòng Cassandra.
- Vận hành resharding là chuyển **hash slots và keys** tương ứng.
- Multi-key operations thường phải tuân thủ điều kiện cùng slot theo quy tắc Redis Cluster.

## 29. Redis hash tags: chủ động đặt các key liên quan cùng slot

Redis Cluster có cú pháp **hash tag**: một đoạn giữa cặp ngoặc nhọn hợp lệ trong key được dùng để xác định hash slot.

Ví dụ:

~~~text
user:{42}:cart
user:{42}:favorites
user:{42}:settings
~~~

Các key có cùng hash tag `42` được đưa về **cùng hash slot** theo quy tắc Redis Cluster.

Điều này có ích nếu cần thao tác nhiều key liên quan trong cùng phạm vi mà Redis Cluster hỗ trợ.

### Cái giá của hash tag quá rộng

Nếu mọi key đều dùng:

~~~text
{all-users}:...
~~~

thì tất cả có thể bị ghép vào **một slot**, gây hotspot và làm mất mục tiêu phân tán.

**Giống cách chọn partition key:** co-location giúp thao tác cùng nhau nhưng có thể gây mất cân bằng nếu nhóm quá lớn/nóng.

### Slot migration và chuyển tiếp

Khi slot được chuyển từ node A sang B, client có thể nhận phản hồi định tuyến như `MOVED`/`ASK` theo trạng thái cluster và migration. Driver Redis Cluster có khả năng xử lý lại routing map theo quy tắc hỗ trợ.

Không hardcode slot owner lâu dài trong ứng dụng; resharding hoặc failover có thể làm chủ sở hữu thay đổi.

## 30. MongoDB hashed sharding: cùng mục tiêu, thuật toán khác

**MongoDB** hỗ trợ **hashed sharding** trên shard key. Phần key được hash phục vụ phân phối dữ liệu; các **chunks/ranges** của không gian shard key được gán cho những shards và có cơ chế cân bằng/migration.

Ví dụ cú pháp minh họa (đòi cluster đã cấu hình sharding và các điều kiện version/index phù hợp):

~~~javascript
sh.shardCollection(
  "shop.orders",
  { customerId: "hashed" }
);
~~~

Đường đi khái niệm:

~~~text
customerId
   |
   v
Hashed shard-key value
   |
   v
Chunk/range metadata
   |
   v
Shard owner
   |
   v
mongos/router (trong kiến trúc dùng mongos)
~~~

### Không gọi mọi hashed sharding là consistent hashing ring

MongoDB hashed sharding, Redis hash slots và Cassandra token ring có mục tiêu chung là **phân phối key và định tuyến**, nhưng khác:

- Đơn vị ownership: chunk, slot, token range.
- Bảng metadata/placement.
- Quy trình rebalance/migration.
- Replication và consistency model.
- Cách driver/router truy cập.

Việc khóa được hash không đồng nghĩa hệ sử dụng vnodes trên một vòng consistent hashing theo đúng thuật toán Cassandra.

### Hashed shard key có đánh đổi truy vấn

Hash giúp phân tán những khóa có phân bố tăng dần hoặc pattern dễ tạo một shard nóng. Nhưng query theo một **khoảng giá trị gốc** có thể không còn được gom vào một dải shard liên tục như range sharding.

Khi chọn shard key cần cân nhắc:

- Point lookup có đầy đủ shard key không?
- Query theo tenant, thời gian hoặc customer có cần nhiều shard?
- Một customer có nhiều dữ liệu có trở thành hot key không?
- Unique constraint/index và migration có những giới hạn nào ở phiên bản DBMS?

## 31. Managed NoSQL: không suy đoán thuật toán nội bộ

Một dịch vụ như Amazon DynamoDB quản lý partitioning, placement và scaling theo cơ chế riêng. Người dùng có thể chọn partition key/schema và một số cấu hình năng lực, nhưng không nên tự khẳng định:

~~~text
DynamoDB luôn sử dụng chính xác vòng Cassandra
hoặc
Node vật lý A có 256 vnode
~~~

nếu không có tài liệu chính thức xác nhận cho đúng dịch vụ và thời điểm.

Nguyên tắc học:

1. **Đọc hợp đồng công khai:** partition key, giới hạn item/throughput, consistency, API.
2. **Không gán thuật toán không công khai** chỉ vì có cùng tên “hash partitioning”.
3. **Thiết kế key** để tránh skew/hot partitions dù service tự quản placement.
4. **Đo workload** thay vì suy rằng managed scaling loại bỏ mọi hotspot.

## 32. So sánh bốn kiểu ánh xạ key

| Chiến lược | Đơn vị ánh xạ | Khi thêm node/shard | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `hash(key) % N` trực tiếp | Node index theo N | N đổi có thể remap phần lớn key | Đơn giản nhưng membership động khó |
| Consistent hashing ring | Token range → node | Chủ yếu những ranges liên quan đổi owner | Cần placement, migration, replica semantics |
| Fixed hash slots | Key → slot → node | Chuyển slot ownership, hash key ổn định | Slot count/granularity, multi-key locality |
| Hashed shard key + chunks | Hashed key → chunk/range → shard | Split/move chunks theo metadata | Query routing và rebalance theo DBMS |

Ngoài ra còn có các họ thuật toán khác:

- **Rendezvous hashing / highest-random-weight hashing:** tính điểm của key đối với từng candidate node và chọn node có điểm phù hợp. Thay đổi membership có thể giúp giữ mapping ổn định nhưng chi phí tính/triển khai khác.
- **Jump consistent hash:** ánh xạ key sang bucket index với đặc tính thay đổi mapping nhỏ khi số bucket thay đổi theo mô hình phù hợp; có hạn chế về loại ID/trọng số/membership không tuần tự.
- **Directory-based sharding:** dùng một bảng mapping partition ID → node, cho phép di chuyển từng partition logic.

**Không phải mọi thuật toán giảm remapping đều dùng token ring hoặc vnodes**. Chọn thuật toán theo yêu cầu, topology và đặc tính DBMS.

## 33. Hot partition: lý do hashing và vnodes chưa đủ

Giả sử một ứng dụng sự kiện có 1 triệu khách hàng. 999.999 khách ghi ít, nhưng một khách hàng lớn ghi 50.000 sự kiện/giây vào:

~~~text
partitionKey = "tenant:VIP"
~~~

Token của `VIP` vẫn chỉ là **một token**, thuộc một tập replica cố định.

~~~text
tenant:VIP
    |
    v
hash → token 42
    |
    v
Replica set của token 42
~~~

Nếu tăng số vnode trên các node nhưng không đổi partition key, mọi event có cùng partition key vẫn tới **cùng một partition logic**. Workload có thể quá nóng tại những replica của key đó.

### Giải pháp partitioning nghiệp vụ

Có thể chia theo bucket:

~~~text
partitionKey = (tenant_id, bucket_id)
bucket_id    = hash(event_id) % 16
~~~

Khi ấy một tenant có thể được phân bố trên 16 partition keys, mỗi key hash độc lập. Nhưng đổi lại:

- Query tất cả event của tenant cần đọc/gộp nhiều buckets.
- Giữ đúng thứ tự thời gian toàn tenant khó hơn.
- Nâng từ 16 lên 32 buckets cần chiến lược đọc dữ liệu cũ và dữ liệu mới.
- Các phép cập nhật quota toàn tenant không tự nguyên tử trên nhiều buckets.

**Bài toán partition key là bài toán mô hình dữ liệu và access pattern**, không chỉ chuyện thuật toán token.

## 34. Chọn composite partition key theo truy vấn

Ví dụ đơn hàng:

~~~text
Option A:
  partitionKey = tenant_id

Option B:
  partitionKey = (tenant_id, customer_id)

Option C:
  partitionKey = (tenant_id, customer_id, month_bucket)
~~~

| Lựa chọn | Lợi ích | Rủi ro/đánh đổi |
| --- | --- | --- |
| `tenant_id` | Các dữ liệu cùng tenant cùng vị trí logic | Tenant lớn tạo partition quá to/hot |
| `(tenant_id,customer_id)` | Phân tán theo customer, query đơn hàng một customer thuận lợi | Query toàn tenant cần nhiều partitions |
| `(...,month_bucket)` | Giới hạn partition theo thời gian, phù hợp retention | Query nhiều tháng fan-out; bucket hiện tại có thể nóng |

Khi chọn key, phải phân tích:

1. Cardinality: có bao nhiêu partition keys thực?
2. Phân bố kích thước theo key.
3. Phân bố read/write QPS theo key.
4. Độ lớn partition tối đa.
5. Tần suất query xuyên partition.
6. Nhu cầu transaction/quota, ordering và retention.

Không nên chỉ dựa vào “hash sẽ tự rải đều” để chọn key.

## 35. Consistent hashing và rebalancing là hai bước khác nhau

**Consistent hashing** tính ra ai nên giữ một token range.

**Rebalancing/migration** làm cho dữ liệu vật lý thực sự được chuyển tới đúng nơi.

~~~text
Membership changed
      |
      v
Token/owner map updated
      |
      v
New node assigned ranges
      |
      v
Streaming / copy / catch-up
      |
      v
Consistency/repair verification
      |
      v
Safe cutover / cleanup
~~~

Nếu chỉ đổi owner map mà không chuyển dữ liệu, một lookup có thể đến node mới nhưng không tìm thấy bản ghi cũ.

Nếu chỉ chuyển dữ liệu mà router vẫn dùng metadata cũ, request có thể tiếp tục tới node không còn là owner.

### Trong giai đoạn migration có thể có nhiều nguồn hợp lệ

DBMS có thể cần trạng thái chuyển tiếp:

- Source còn phục vụ trong lúc target đang bắt kịp.
- Một số request được redirect.
- Write mới phải được ghi/forward sao cho không bị mất.
- Snapshot và delta/log catch-up có mốc kiểm soát.
- Cleanup chỉ xảy ra sau khi target an toàn.

Người viết ứng dụng không được tự phát minh một cutover chỉ bằng cách cập nhật bảng key → node nếu không giải quyết concurrent writes.

## 36. Tại sao vnode count ảnh hưởng streaming load?

Giả sử một node cũ giữ một đoạn rất lớn:

~~~text
Node A: một range chiếm 500 GiB
~~~

Thêm node mới có thể khiến A phải chuyển một phần lớn range cho node mới. Trong hệ vnodes:

~~~text
Node A: nhiều ranges, mỗi range một phần dữ liệu
Node B: nhiều ranges
Node C: nhiều ranges

Node D mới có thể nhận:
  một số ranges từ A
  một số ranges từ B
  một số ranges từ C
~~~

Về mặt lý thuyết, nhiều nguồn có thể song song góp dữ liệu. Nhưng network/disk tổng vẫn có thể là nút thắt, và nhiều streams cùng lúc có thể làm latency request production tăng.

**Khả năng rebalance tốt không có nghĩa rebalance miễn phí.** Cần có giới hạn streaming, headroom disk, theo dõi compaction và kế hoạch rollback theo sản phẩm.

## 37. Khi thay RF, placement và ownership vẫn phải được xác minh

Ví dụ Cassandra tăng RF trong DC:

~~~sql
ALTER KEYSPACE shop
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hcm': 3
};
~~~

Sau khi thay metadata, những replica mới có thể cần **repair/streaming** để có đủ dữ liệu theo hướng dẫn của đúng phiên bản.

Phân biệt:

- **Tăng RF:** có thêm replica cho mỗi partition, khác với thêm partition key.
- **Thêm node:** tăng năng lực vật lý và có thể thay token owner map.
- **Thêm vnode:** thay granularity token ownership trên node, không tăng số bản sao mỗi key chỉ vì có thêm token.
- **Rebuild/repair:** đưa nội dung dữ liệu ở các replica về trạng thái thích hợp.

Những thao tác trên **không tương đương**, và không nên làm đồng thời trên production khi chưa có kế hoạch điều phối.

## 38. Dung lượng với RF và vnode

Giả sử dataset logic có 12 TiB, RF=3 trong một DC và 12 data-bearing nodes đồng cấu hình.

Một ước lượng thô:

\[
\text{Replicated bytes}\approx12\text{ TiB}\times3=36\text{ TiB}
\]

Dung lượng trung bình:

\[
\frac{36\text{ TiB}}{12\text{ nodes}}=3\text{ TiB/node}
\]

**Không nên lấy 3 TiB làm dự báo chính xác** vì còn:

- Metadata/index/commit log.
- Tombstones, SSTable versions, compaction.
- Dữ liệu skew và hot partitions.
- Snapshot/backup.
- Repair/bootstrap temporary space.
- Node down khiến dữ liệu cần rebuild nơi khác.

Vnodes có thể cải thiện việc phân phối **range ownership**, nhưng số byte thực có thể lệch. **RF quyết định xu hướng nhân bản dung lượng**, còn vnode count không đơn giản nhân bản số byte.

## 39. Vnode không phải replica: một phản ví dụ quan trọng

Một node A có 64 vnode tokens:

~~~text
Node A:
  vnode A1
  vnode A2
  ...
  vnode A64
~~~

Nếu Node A chết, **tất cả 64 vnode trên A cùng không phục vụ**.

Điều đó khác:

~~~text
Replica 1: Node A
Replica 2: Node B
Replica 3: Node C
~~~

Với RF=3 trải trên ba node, mất A còn B,C. Với 64 vnodes nhưng chỉ một bản sao vật lý của mỗi partition, mất A có thể khiến các partitions A chịu trách nhiệm mất bản sao.

**Không đếm virtual nodes như 64 replicas độc lập.**

## 40. Vnode và data locality: không phải mọi truy vấn nên rải đều

Một số truy vấn có lợi nếu dữ liệu liên quan cùng partition:

~~~text
GET all orders of one customer
GET latest events in one device/time bucket
UPDATE account aggregate atomically
~~~

Nếu dùng partition key rải tất cả hàng theo `order_id` thay vì `customer_id`, dữ liệu một khách có thể nằm trên nhiều partitions:

- Point lookup theo order ID dễ định tuyến.
- Query mọi đơn của khách có thể cần secondary index/read model/fan-out.
- Transaction liên quan nhiều đơn có thể có ranh giới khác.

**Consistent hashing tối ưu ánh xạ của những partition keys đã chọn**, không quyết định cho ta nên nhóm hàng nào thành một partition.

Đây là lý do mô hình dữ liệu NoSQL thường thiết kế **theo truy vấn trước, chọn partition key, rồi mới đánh giá hashing/placement**.

## 41. Java: mô phỏng vòng consistent hashing

Đoạn mã sau là **thí nghiệm giáo dục** về token ring; nó không triển khai Cassandra Murmur3Partitioner hay replication.

Để dễ đối chiếu với bảng tính tay, ta dùng miền token **0..99** và bốn node ở token 10,35,60,85. Mã dùng `CRC32` để biến chuỗi key thành số không âm rồi lấy modulo 100; đó chỉ là hàm hash **đơn giản cho lab**, không nên dùng như routing hash của một DBMS production.

Tạo file `ConsistentHashRingDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;
import java.util.zip.CRC32;

public final class ConsistentHashRingDemo {

    private static final int TOKEN_SPACE = 100;
    private final NavigableMap<Integer, String> ring =
            new TreeMap<>();

    public void addToken(int token, String nodeId) {
        if (token < 0 || token >= TOKEN_SPACE) {
            throw new IllegalArgumentException("Invalid token");
        }
        if (ring.containsKey(token)) {
            throw new IllegalArgumentException("Token collision");
        }
        ring.put(token, nodeId);
    }

    public static int tokenForKey(String key) {
        CRC32 crc = new CRC32();
        byte[] bytes = key.getBytes(StandardCharsets.UTF_8);
        crc.update(bytes, 0, bytes.length);
        return (int) (crc.getValue() % TOKEN_SPACE);
    }

    public String ownerOfToken(int token) {
        if (ring.isEmpty()) {
            throw new IllegalStateException("Empty ring");
        }
        if (token < 0 || token >= TOKEN_SPACE) {
            throw new IllegalArgumentException("Invalid token");
        }

        // First node token >= key token; wrap to first entry.
        Map.Entry<Integer, String> entry =
                ring.ceilingEntry(token);
        if (entry == null) {
            entry = ring.firstEntry();
        }
        return entry.getValue();
    }

    public String ownerOfKey(String key) {
        return ownerOfToken(tokenForKey(key));
    }

    public static void main(String[] args) {
        ConsistentHashRingDemo ring =
                new ConsistentHashRingDemo();
        ring.addToken(10, "A");
        ring.addToken(35, "B");
        ring.addToken(60, "C");
        ring.addToken(85, "D");

        System.out.println("token=7  owner=" +
                ring.ownerOfToken(7));
        System.out.println("token=38 owner=" +
                ring.ownerOfToken(38));
        System.out.println("token=73 owner=" +
                ring.ownerOfToken(73));
        System.out.println("token=96 owner=" +
                ring.ownerOfToken(96));

        // Snapshot ownership of 1,000 sample keys.
        Map<String, String> before = new TreeMap<>();
        for (int i = 0; i < 1000; i++) {
            String key = "order-" + i;
            before.put(key, ring.ownerOfKey(key));
        }

        // Add new node E between B@35 and C@60.
        ring.addToken(48, "E");

        int moved = 0;
        for (Map.Entry<String, String> item : before.entrySet()) {
            String afterOwner = ring.ownerOfKey(item.getKey());
            if (!item.getValue().equals(afterOwner)) {
                moved++;
                // Only the old C range (35,48] may move to E.
                if (!"C".equals(item.getValue())
                        || !"E".equals(afterOwner)) {
                    throw new AssertionError("Unexpected movement");
                }
            }
        }
        System.out.println("Moved keys after E@48: " + moved);
    }
}
~~~

Chạy:

~~~bash
javac ConsistentHashRingDemo.java
java ConsistentHashRingDemo
~~~

Các dòng đầu dự kiến:

~~~text
token=7  owner=A
token=38 owner=C
token=73 owner=D
token=96 owner=A
Moved keys after E@48: <một số từ 0 đến 1000>
~~~

Dòng cuối phụ thuộc kết quả CRC32 trên 1.000 sample keys, nhưng chương trình cố ý kiểm tra rằng **nếu owner thay đổi, nó chỉ chuyển C→E** theo quy tắc và vị trí token đã chọn.

### Sửa thí nghiệm

1. Thay token E từ 48 sang 58 và chạy lại; số key chuyển thay đổi thế nào?
2. Thêm một token mới 0; những key nào có thể đổi owner?
3. Xóa token C@60 rồi so quyền sở hữu với vòng trước.
4. Tăng miền token lên 1.000 để quan sát độ mịn biểu diễn.
5. Thêm nhiều token cho cùng Node A/B/C; so độ dài ownership ranges mỗi node.

**Không áp dụng CRC32 mod 100 để phân chia dữ liệu thực**. Không gian nhỏ có collision nhiều; mục đích ở đây là hiểu thuật toán.

## 42. Java: mở rộng mô hình với virtual nodes

Giữ cùng kiểu `TreeMap`, nhiều vnode đơn giản là **nhiều entry token trỏ tới cùng một node vật lý**.

Ý tưởng:

~~~java
ConsistentHashRingDemo ring =
        new ConsistentHashRingDemo();

ring.addToken(10, "A");
ring.addToken(50, "A");

ring.addToken(25, "B");
ring.addToken(65, "B");

ring.addToken(40, "C");
ring.addToken(80, "C");
~~~

Hàm `ownerOfToken` vẫn hoạt động, vì nó chọn token entry đầu tiên lớn hơn hoặc bằng token key, rồi trả `nodeId` tương ứng.

### Đếm độ dài ownership trên vòng minh họa

Với token 0..99:

| Node | Các khoảng | Tổng số token nguyên |
| --- | --- | ---: |
| A | (80,10] và (40,50] | 30 + 10 = 40 |
| B | (10,25] và (50,65] | 15 + 15 = 30 |
| C | (25,40] và (65,80] | 15 + 15 = 30 |

Node A sở hữu 40% token universe, B/C mỗi node 30%. Ví dụ này cho thấy **nhiều vnode không tự đảm bảo phân bố chính xác bằng nhau**; vị trí token quyết định tổng ownership.

### Token collision khi tạo vnode

Nếu hai vnode được hash vào **đúng cùng một token**, cần quy tắc xử lý, phát hiện hoặc chọn lại token. Trong code `addToken` ta chủ động ném lỗi để tránh vô tình ghi đè owner.

Trong hệ token 64 bit với phân bố tốt, xác suất collision thấp hơn nhiều so với miền 0..99, nhưng không được suy rằng collision không thể xảy ra. Cơ chế token allocation/metadata của DBMS phải xử lý hợp lệ.

## 43. Kịch bản nhiều node vật lý nhưng không đủ cân bằng

Giả sử mỗi node giữ cùng số vnodes nhưng workload thực:

~~~text
Node A: nhiều partition nhỏ  → CPU 20%
Node B: ít partition lớn     → disk 85%
Node C: một hot partition    → CPU 95%
~~~

Ring có thể trông cân bằng theo số token hoặc ownership %, nhưng hệ vẫn gặp bottleneck.

### Điều phải đo

- Disk bytes mỗi node và mỗi table.
- QPS/latency theo partition key.
- Hot reads/writes.
- SSTable/compaction backlog.
- Network in/out và streaming.
- Cache hit rate, memory pressure.
- Kích thước partition lớn nhất.

Phương án giải quyết phụ thuộc nguyên nhân:

- **Uneven token ranges:** xem vnode/token allocation.
- **Partition-size skew:** thiết kế lại partition key hoặc bucketing.
- **Single hot key:** cache, sharded counter, serialization/coordination hoặc mô hình write khác.
- **Unequal nodes:** xem capacity weighting/tooling theo DBMS.
- **Large cross-partition queries:** tạo read model phù hợp access pattern.

Đừng tự động “tăng vnode lên gấp 10” khi chưa biết vấn đề là token balance hay hot key.

## 44. Khi một node hỏng, replica khác xử lý gì?

Ví dụ Cassandra RF=3:

~~~text
Partition P replicas:
  A (UP)
  B (UP)
  C (DOWN)
~~~

Nếu read/write cần `LOCAL_QUORUM` trong DC RF=3, ngưỡng số học là 2. A/B **có thể** đáp ứng khi cùng reachable và những điều kiện giao thức khác thỏa.

Tuy nhiên:

- Không được coi A/B là hai vnodes trên cùng host.
- Phải xét version consistency và write acknowledgment.
- Node C cần bắt kịp khi hồi phục.
- Nếu thêm một node D để thay C, dữ liệu cần được stream/repair.

**Virtual nodes giúp phân bố ownership, không thay thế replica redundancy.**

## 45. Thêm node có làm query của client thay đổi không?

Về hợp đồng API, ứng dụng có thể vẫn gọi:

~~~text
getOrder(tenantId, customerId, orderId)
~~~

nhưng token map phía dưới đổi khi scale.

### Thiết kế đúng

- Driver/coordinator cập nhật topology metadata.
- Routing key vẫn được tính theo partition key.
- Query không hardcode địa chỉ của một node cho một customer.
- Retry định tuyến tuân theo semantics của driver.
- Định danh business key không bị đổi chỉ vì owner vật lý thay đổi.

### Thiết kế dễ lỗi

~~~text
customer C42 → luôn gọi node-3.company.local
~~~

Nếu node-3 decommission hoặc key của C42 chuyển sang replica khác, mapping tĩnh có thể sai.

**Shard placement là chi tiết hạ tầng có thể thay đổi**, trong khi **business key cần ổn định**.

## 46. Lỗi điều hành: tăng node nhưng chưa chuyển dữ liệu

Giả sử:

~~~text
T0: Node A sở hữu range R
T1: Metadata đổi, Node D được giao range R
T2: Client route GET key thuộc R tới D
T3: D chưa stream key đó
~~~

Nếu hệ tự triển khai routing không có cơ chế chuyển tiếp/đảm bảo cutover, client có thể nhận false NOT_FOUND.

Trong một DBMS thực, bootstrap/decommission có các bước bảo vệ để tránh tình huống không an toàn. **Không thay thế các quy trình đó bằng việc sửa bảng owner rồi sao chép file thủ công.**

Một kế hoạch migration cần:

1. Chuẩn bị node mới và capacity.
2. Đồng bộ dữ liệu snapshot/range.
3. Bắt kịp các write mới phát sinh trong lúc copy.
4. Xác nhận đủ dữ liệu và topology.
5. Chuyển routing một cách an toàn.
6. Chỉ cleanup ở nguồn khi cutover thành công.

Đây là mô hình khái quát, không phải thứ tự thao tác chuẩn cho mọi Cassandra/Redis/MongoDB version.

## 47. Anti-pattern: coi token là vị trí bất biến của một khách hàng

Một khách hàng có:

~~~text
partitionKey = (tenant=T1, customer=C42)
token = t42
~~~

Token `t42` có thể ổn định nếu partitioner và serialization không đổi. Nhưng **node chịu trách nhiệm cho token đó có thể đổi** khi:

- Thêm/bớt node.
- Rebalance token assignment.
- Thay replication strategy.
- Thay rack/DC topology.
- Failover/routing policy thay đổi.

Không nên lưu trong order document:

~~~json
{
  "customerId": "C42",
  "permanentNode": "node-7"
}
~~~

rồi tin rằng vị trí vật lý là thuộc tính vĩnh viễn của customer.

Nếu ứng dụng cần một **logical shard ID ổn định**, hãy quản lý nó như một abstraction và cho phép logical shard → physical node mapping thay đổi theo thiết kế.

## 48. Phân biệt consistent hashing với rendezvous hashing

Cùng muốn thay đổi ít key khi membership thay đổi, nhưng thuật toán khác nhau.

### Consistent hashing ring

~~~text
hash(key) → token trên vòng
           → successor token node
           → owner
~~~

### Rendezvous / highest-random-weight hashing

~~~text
Với mỗi candidate node n:
    score(key, n) = hash(key + nodeIdentity)

Owner = node có score cao nhất
~~~

Tính chất quan trọng: với hàm score ổn định và thuật toán chọn phù hợp, khi thêm node mới, chỉ những key mà node mới thắng score mới phải đổi owner; các key còn lại giữ nguyên. Khi bỏ node, chủ yếu các key trước đó thuộc node bị bỏ phải chọn owner khác.

Rendezvous hashing không bắt buộc có vòng token hay vnode theo cùng cấu trúc, dù có thể dùng các biến thể trọng số.

### Khi nào so sánh?

| Khía cạnh | Ring consistent hashing | Rendezvous hashing |
| --- | --- | --- |
| Biểu diễn | Token ranges trên vòng | Điểm score per key/candidate |
| Lookup | Tìm successor trên token map | Tính/xếp score candidate |
| Topology change | Chuyển ranges | Key chọn owner mới theo score |
| Weighted variants | Token allocation/weighting | Weighted rendezvous variants |
| Khả năng quan sát | Ownership ranges rõ | Score logic, ít dựa trên range |

Một số biến thể giải quyết lookup hiệu quả cho nhiều nodes; không nên so sánh hiệu năng chỉ bằng sơ đồ đơn giản này.

## 49. “Consistent hashing” không phải “strong consistency”

Hai thuật ngữ dùng chung chữ *consistent*, nhưng là **hai bài toán khác nhau**.

- **Consistent hashing:** ổn định ánh xạ key → vị trí khi số node thay đổi.
- **Consistency model:** những lịch sử đọc/ghi client được phép quan sát, ví dụ linearizability, causal hoặc eventual consistency.

Một hệ dùng consistent hashing vẫn có thể:

- Đọc từ replica stale.
- Cho eventual consistency.
- Có transaction trên một phạm vi.
- Dùng quorum mạnh hơn trong một số thao tác.

**Đừng suy từ tên thuật toán phân mảnh ra bảo đảm transaction hoặc read freshness.**

## 50. Bảo mật và dữ liệu nhạy cảm khi định tuyến

Hash partition key để định tuyến không thay thế:

- Authorization theo tenant/user.
- Mã hóa dữ liệu lưu và truyền.
- Validation ID/routing input.
- Bảo vệ thông tin metadata/topology.
- Rate limiting chống hot-key abuse.

Ví dụ, nếu token của customer C42 dễ đoán, điều đó **không cho client quyền đọc customer C42**. Kiểm tra tenant ownership phải được thực hiện theo security model, không dựa vào việc key nằm trên node nào.

Không dùng Murmur3/token của Cassandra làm **security token** hoặc mã xác thực. Chúng phục vụ phân phối dữ liệu, không phải bí mật mật mã.

## 51. Bài tập thực hành

### Bài 1 — Modulo khi thêm node

Với `h(key)=13,14,15,16,17,18`, tính owner theo `hash % 4` và `hash % 5`. Đếm số key đổi owner.

**Gợi ý:** số dư modulo thường thay đổi khi N đổi; vì vậy cách chia trực tiếp theo N dễ remap nhiều key.

### Bài 2 — Vòng token cơ bản

Không gian 0..99 với A@10, B@35, C@60, D@85. Tìm owner của token 0, 10, 11, 35, 36, 60, 61, 85, 86 và 99.

**Gợi ý:** dùng khoảng (previous,current] và nhớ wrap-around.

### Bài 3 — Biên vòng

Node A@10 có predecessor D@85. Viết chính xác tập token nguyên thuộc A và giải thích vì sao `85` không thuộc A nhưng `86` và `10` thuộc.

**Gợi ý:** (85,10] gồm 86..99 và 0..10.

### Bài 4 — Thêm node

Thêm E@48 vào vòng A@10, B@35, C@60, D@85. Tập token nào đổi owner? Tập nào giữ nguyên?

**Gợi ý:** chỉ (35,48] đổi từ C sang E trong mô hình một bản sao.

### Bài 5 — Bỏ node

Sau khi thêm E@48, bỏ C@60. Khoảng nào đổi owner và owner mới là ai?

**Gợi ý:** (48,60] chuyển từ C sang D@85.

### Bài 6 — Vì sao một token/node lệch?

Xét A@10, B@12, C@70, D@85. Tính độ dài range mỗi node trong miền 0..99. Node nào chịu nhiều token nhất?

**Gợi ý:** C có khoảng (12,70], dài 58 token.

### Bài 7 — Vnodes

Ba node: A@10,@50; B@25,@65; C@40,@80. Liệt kê sáu khoảng sở hữu và tính tổng số token của từng node.

**Gợi ý:** A=40, B=30, C=30 trong miền 100 token minh họa.

### Bài 8 — Vnode khác replica

Một node có 64 vnodes. Nếu host chết, có phải còn 63 bản sao của dữ liệu trên những vnode khác của host không?

**Gợi ý:** vnode là phân đoạn ownership logic; cùng host chết thì mọi vnode trên host đều bị ảnh hưởng.

### Bài 9 — Cassandra partition key

Cho bảng:

~~~sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    order_id text,
    total_minor bigint,
    PRIMARY KEY ((tenant_id, customer_id), order_id)
);
~~~

Hai order khác nhau cùng tenant/customer có cùng token hay khác token? Tại sao?

**Gợi ý:** token xác định bằng **partition key** là cặp tenant/customer; clustering key không làm đổi token.

### Bài 10 — Hot partition

Một tenant gửi 50.000 event/giây với cùng partition key. Nếu tăng từ 16 lên 256 vnodes/node, liệu một partition key đó tự tách thành 16 partition? Đề xuất cách khác.

**Gợi ý:** partition key không đổi; cần thiết kế bucket/sharded counter hoặc mô hình write phù hợp.

### Bài 11 — Replication và rack

Một DC có ba rack, RF=3 và LOCAL_QUORUM=2. So sánh placement 1–1–1 với 2–1–0 khi mất rack có hai replica.

**Gợi ý:** còn 2 so với còn 1; rack-awareness quyết định khả năng đáp ứng quorum.

### Bài 12 — Thêm node mà chưa stream

Owner map mới chuyển range R từ A sang D, nhưng D chưa nhận dữ liệu. Nếu router đã chuyển toàn bộ GET sang D, lỗi gì có thể xuất hiện?

**Gợi ý:** false NOT_FOUND/stale data; migration cần catch-up và cutover an toàn.

### Bài 13 — Redis Cluster

Tại sao Redis Cluster dùng 16.384 hash slots nhưng không nên gọi đó là Cassandra vnode ring? Thêm một Redis node thường liên quan tới thao tác gì?

**Gợi ý:** cố định slot universe, slot→node metadata và reshard/migration.

### Bài 14 — Hash tags

Hai key `user:{42}:cart` và `user:{42}:favorites` có cùng Redis hash slot không? Nếu mọi user dùng tag `{all}`, điều gì bất lợi?

**Gợi ý:** cùng tag 42; tag chung cho toàn hệ tạo hotspot tại một slot.

### Bài 15 — MongoDB hashed sharding

So sánh hashed shard key với Cassandra token ring về đơn vị quản lý, cách cân bằng và ảnh hưởng tới range queries.

**Gợi ý:** MongoDB hashed values được nhóm thành chunks và di chuyển theo metadata; không đồng nhất với vnode tokens.

### Bài 16 — Consistent hashing và linearizability

Vì sao việc một key luôn được định tuyến đến cùng token owner trong một topology không chứng minh lần đọc sau ghi luôn thấy giá trị mới nhất?

**Gợi ý:** replica lag, consistency level và commit protocol là vấn đề riêng.

### Bài 17 — Dung lượng

Dataset logic 12 TiB, RF=3, 12 node. Ước tính replicated bytes và bytes trung bình/node trước overhead. Những giới hạn nào khiến số đo thật khác?

**Gợi ý:** 36 TiB tổng, 3 TiB/node; skew, WAL, compaction, snapshot, repair.

### Bài 18 — RF và vnode count

Một keyspace có RF=3. Node A tăng từ 8 lên 32 vnode. Có phải mỗi partition được sao thành 12 bản không?

**Gợi ý:** không; RF và vnode count là hai chiều độc lập.

### Bài 19 — Token collision

Mô hình lab dùng token 0..99. Hai vnode được gán token 35. Cần xử lý gì? Vì sao không thể im lặng ghi đè entry trong TreeMap?

**Gợi ý:** collision trong node token metadata cần được phát hiện/điều phối theo quy tắc, nếu không đổi owner sai.

### Bài 20 — Bài tập Java

Chạy chương trình `ConsistentHashRingDemo`. Thêm E@48 rồi thay E@58. Ghi số sample keys đổi owner và kiểm tra chúng xuất phát từ node nào.

**Gợi ý:** trong mô hình một bản sao, chỉ một đoạn của vùng C đổi owner; số sample keys phụ thuộc phân bố hash.

### Bài 21 — Thêm một DC

Cassandra keyspace có RF=3 ở DC-A và mới thêm DC-B RF=3. Chỉ đổi metadata có đủ để DC-B phục vụ mọi dữ liệu cũ chưa?

**Gợi ý:** cần đủ node/topology, streaming/repair/verification và routing/consistency contract phù hợp.

### Bài 22 — Chọn partition key theo truy vấn

Một hệ cần “xem 100 đơn gần nhất của một khách” và “thống kê mọi đơn của tenant”. Đề xuất partition key, read model hoặc phép tổng hợp phù hợp. Tại sao không nên rải từng order ID ngẫu nhiên rồi dùng full scan cho cả hai truy vấn?

**Gợi ý:** tối ưu access pattern quan trọng trước; hashing không biến scan xuyên partition thành rẻ.

### Bài 23 — Failure domain

Một cluster có RF=3 trên ba VM, cả ba cùng AZ. Có thể chịu lỗi một VM không? Có chịu mất cả AZ không? Việc tăng vnodes có giải quyết lỗi AZ không?

**Gợi ý:** những lỗi có phạm vi khác nhau; vnode không tạo failure domains vật lý mới.

### Bài 24 — Bài toán triển khai

Hệ NoSQL cho thuê có 10 triệu tài sản, cần lookup theo `listingId`, lọc theo khu vực và cập nhật giá theo `listingId`; phải mở rộng từ 6 lên 12 node.

Hãy phân tích:

1. Partition key nào phù hợp point lookup?
2. Lookup theo khu vực cần secondary index/read model gì?
3. Hash/token và vnode giúp gì khi thêm node?
4. Một listing cực nóng có tự được chia ra nhiều node không?
5. Rebalancing cần quản lý read/write trong lúc di chuyển thế nào?
6. RF, rack placement, quorum và backup bảo vệ những lỗi nào?

**Gợi ý:** không có một hash function thay thế được việc thiết kế dữ liệu theo truy vấn và consistency.

## 52. Checklist thiết kế consistent hashing / token partitioning

Trước khi triển khai hoặc sửa topology, hãy trả lời:

| Câu hỏi | Điều cần ghi rõ |
| --- | --- |
| Dữ liệu dùng partition key nào? | Kiểu, serialization, cardinality |
| Hash/partitioner là gì? | Tên thuật toán và phiên bản DBMS |
| Token universe và biên range? | Số/kiểu token, mở/đóng, wrap-around |
| Ownership map được lưu ở đâu? | Driver, coordinator, routing metadata |
| Một node có bao nhiêu vnodes? | Cấu hình và phương pháp cấp token |
| Có node khác cấu hình không? | Capacity/weighting policy |
| Một partition có bao nhiêu replica? | RF theo DC/cluster |
| Rack/DC placement ra sao? | Snitch labels và failure domains thực |
| Read/write cần consistency gì? | QUORUM, LOCAL_QUORUM, strong/session... |
| Thêm node cần di chuyển những ranges nào? | Bootstrap/streaming plan |
| Cắt chuyển routing lúc nào? | Safe cutover, catch-up, retries |
| Có theo dõi hot partitions không? | QPS, size, latency theo key |
| Repair và tombstones được quản lý ra sao? | Frequency, retention, lag |
| Nếu mất node/rack/DC thì sao? | Failure matrix, recovery objectives |
| Driver có token-aware routing không? | Prepared/bound keys, local DC |
| Backup/restore có độc lập replication không? | DR drills |
| Có chính sách dữ liệu vùng/quốc gia không? | Residency, backup/CDC constraints |

**Không kết luận “hệ cân bằng và chịu lỗi tốt” chỉ từ RF hoặc vnode count.** Cần quan sát replica map, workloads và các kịch bản sự cố thực.

## 53. Những hiểu nhầm thường gặp

| Nhận định | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Consistent hashing nghĩa dữ liệu luôn nhất quán.” | Nhầm hashing với consistency model | Hashing nói về placement/remapping |
| “Hash modulo N là consistent hashing ring.” | Khi N đổi, nhiều key đổi owner | Ring/fixed slots/directory giải quyết remapping theo cách khác |
| “Một token ảo là một máy ảo.” | Vnode là vị trí/range logic | Một máy có thể giữ nhiều vnodes |
| “256 vnodes là 256 replicas.” | Vnode count khác RF | Một key vẫn có replica set theo RF |
| “Vnodes tự chia một hot key.” | Cùng partition key vẫn có một token | Thiết kế lại key/buckets |
| “Thêm node thì dữ liệu tự chuyển ngay.” | Metadata không phải bytes | Cần streaming/repair/cutover |
| “Cassandra mọi replica là ba node kế tiếp.” | Rack/DC strategy có điều kiện | Dựa vào token map và replication strategy |
| “LOCAL_QUORUM đếm các vnodes của một host.” | Quorum theo replica tham gia, không phải token entries | Cần replica ở các node thích hợp |
| “Một node UP chắc chắn có dữ liệu mới.” | Có thể đang lag/repair | Kiểm freshness/health |
| “Redis Cluster là vòng vnode Cassandra.” | Redis dùng 16.384 slots | Hiểu slot map và hash tags |
| “MongoDB hashed sharding giống hệt ring.” | MongoDB dùng hashed shard-key chunks | Xem routing/chunk migration |
| “Mọi managed NoSQL đều dùng Murmur3.” | Chi tiết nội bộ khác hoặc không công khai | Dựa vào API/documentation được hỗ trợ |
| “Token hash là bí mật bảo mật.” | Hash phân phối không phải encryption | Kiểm auth/authorization riêng |
| “Đổi RF xong là đủ bản sao.” | Replica mới có thể chưa có dữ liệu cũ | Repair/streaming/verify |
| “Tăng RF đồng nghĩa tăng số failure domains.” | Replicas có thể cùng rack/AZ | Anti-affinity theo hạ tầng thực |
| “Vòng cân bằng token nên disk/QPS cân bằng.” | Partition sizes/hotness có thể lệch | Đo data/traffic theo key |
| “Consistent hashing tự bảo đảm ACID.” | Transaction và isolation là bài toán khác | Thiết kế invariants/transactions riêng |

## 54. Tổng kết

**Consistent hashing, token ranges và vnodes** là bộ khái niệm cốt lõi để hiểu cách một số hệ NoSQL phân phối dữ liệu và mở rộng cụm:

1. **Consistent hashing** ánh xạ partition keys và các điểm đại diện node vào không gian token dạng vòng, để khi thêm hoặc bỏ node, một phần tương đối nhỏ key đổi owner.
2. **Token range** là đoạn hash space gắn với một owner theo quy ước biên chính xác. Với quy tắc (previous,current], phải xử lý wrap-around ở cuối vòng.
3. **Virtual nodes** cho phép một node vật lý sở hữu nhiều token ranges không liền nhau, giúp phân bố ownership và streaming từ nhiều vị trí, nhưng thêm metadata/repair overhead.
4. **Vnode khác replica.** RF xác định số bản sao; vnode count xác định granularity ownership; rack/DC awareness xác định failure domains; quorum xác định yêu cầu phối hợp đọc/ghi.
5. **Cassandra** là ví dụ tiêu biểu về Murmur3Partitioner, token ranges, NetworkTopologyStrategy, rack-aware replica placement và token-aware driver routing. Cần hiểu đúng partition key, clustering key và topology metadata.
6. **Redis Cluster** dùng cố định 16.384 hash slots và slot-to-node mapping; **MongoDB hashed sharding** dùng hashed shard key và chunk metadata. Hai hệ này không nên bị mô tả như bản sao chính xác của Cassandra vnode ring.
7. **Consistent hashing không tự sửa hot partition**. Một key quá nóng vẫn tới cùng replica set; hãy chọn partition keys/bucketing dựa trên access pattern.
8. **Khi thêm/xóa node, phải chuyển dữ liệu thật** qua bootstrap/streaming/repair theo giao thức; metadata update không tự đảm bảo cutover an toàn.
9. **Hashing không đồng nghĩa consistency mạnh.** Read freshness, transaction isolation, durability, authorization và idempotency phải được thiết kế ở những lớp tương ứng.

**Nguyên tắc thực hành:** muốn hiểu hoặc cải thiện một cluster NoSQL, hãy vẽ **partition key → hash token → token range → replica set → node/rack/DC**, rồi thử mô phỏng **thêm node, mất node, thêm vnode và mất rack**. Khi xác định được **key nào đổi owner, dữ liệu nào phải stream và còn đủ replica/quorum không**, bạn đã hiểu được bản chất của consistent hashing thay vì chỉ nhớ hình ảnh “vòng tròn hash”.
