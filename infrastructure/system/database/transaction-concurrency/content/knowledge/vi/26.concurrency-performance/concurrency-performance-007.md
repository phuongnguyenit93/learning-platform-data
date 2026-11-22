# Phân chia điểm tranh chấp và đánh đổi đối với bất biến nghiệp vụ

Khi nhiều transaction cùng cập nhật một hàng, một khóa hoặc một tài nguyên, database phải điều phối chúng. Nếu mọi request đều ghi vào cùng một điểm, throughput có thể bị giới hạn dù hệ thống còn nhiều CPU và nhiều node ứng dụng. Một cách tăng khả năng xử lý là phân chia điểm tranh chấp (contention point) thành nhiều điểm nhỏ hơn để các transaction ít phải chờ nhau.

Tuy nhiên, phân chia dữ liệu có thể làm một bất biến nghiệp vụ khó bảo vệ hơn. Ví dụ, thay một bộ đếm tồn kho duy nhất bằng 16 bộ đếm giúp nhiều writer cập nhật song song, nhưng câu hỏi “tổng tồn kho có bao giờ âm không?” giờ liên quan đến nhiều hàng. Nếu chỉ đọc tổng rồi cập nhật một bucket bất kỳ, hai transaction vẫn có thể cùng đưa ra quyết định dựa trên một tổng cũ.

Vì vậy, thiết kế tốt phải trả lời đồng thời hai câu hỏi: **điểm ghi nào đang gây tranh chấp, và quy tắc nghiệp vụ cần được bảo vệ ở phạm vi dữ liệu nào?** Bài học này trình bày các kỹ thuật phân chia điểm ghi, các cách giữ bất biến như quota/escrow và guard, cùng những đánh đổi về độ nhất quán, độ trễ, độ phức tạp và khả năng phục hồi.

## 1. Điểm tranh chấp là gì?

Điểm tranh chấp là một tài nguyên mà nhiều transaction cùng cần truy cập theo cách không thể thực hiện đồng thời hoàn toàn. Tài nguyên có thể là:

- Một hàng được nhiều request cập nhật, chẳng hạn `inventory.quantity` hoặc `account.balance`.
- Một khóa duy nhất trong index, chẳng hạn cùng một email hoặc mã đơn hàng.
- Một hàng tổng hợp dùng làm guard cho bất biến nhiều hàng.
- Một trang/index page bị nhiều thao tác ghi đụng tới.
- Một partition, shard, sequence hoặc bộ cấp phát ID.
- Một hàng queue hoặc trạng thái job mà nhiều worker cùng claim.

Ví dụ một sản phẩm có 10.000 request cùng tăng bộ đếm lượt xem:

```sql
UPDATE product_stats
SET view_count = view_count + 1
WHERE product_id = 42;
```

Phép cộng trong SQL là nguyên tử đối với hàng được cập nhật, nhưng mọi request cho sản phẩm 42 đều tranh chấp cùng hàng. Database phải tuần tự hóa các cập nhật xung đột trên hàng đó. Khi tốc độ ghi cao, thời gian chờ lock và log flush có thể trở thành nút thắt.

Một điểm nóng không nhất thiết là lỗi thiết kế. Nếu hàng đó đại diện cho một tài khoản mà mọi lần trừ/cộng số dư đều phải được tuần tự hóa để bảo vệ bất biến số dư, tranh chấp có thể là chi phí cần thiết. Mục tiêu không phải xóa mọi khóa, mà là giảm tranh chấp ở những nơi có thể phân chia mà vẫn giữ đúng quy tắc nghiệp vụ.

## 2. Nhận diện điểm nóng trước khi phân chia

Không nên nhìn một hàng được cập nhật nhiều rồi lập tức chia nó thành nhiều hàng. Trước tiên cần xác định bottleneck thật sự.

Các tín hiệu thường gặp:

- Lock wait time hoặc số transaction chờ cùng một resource tăng cao.
- Throughput không tăng dù tăng số worker hoặc application instance.
- Một số khóa/business key chiếm phần lớn lượt ghi (hot key/skew).
- Transaction ngắn nhưng thời gian chờ lock lớn.
- CPU chưa bão hòa nhưng latency ghi vẫn cao.
- Một index, sequence hoặc counter được truy cập trong gần như mọi request.
- Queue consumer tăng số worker nhưng throughput không cải thiện vì tất cả cùng claim một hàng.

Hãy phân biệt lock contention với các bottleneck khác như I/O, log flush, CPU, network, connection pool hoặc giới hạn một writer của hệ quản trị. Chia hàng sẽ không giúp nhiều nếu nguyên nhân thật là transaction giữ lock lâu do gọi HTTP hoặc chờ người dùng.

### Đo theo khóa và loại thao tác

Một dashboard hữu ích có thể theo dõi:

| Nhóm | Chỉ số |
| --- | --- |
| Throughput | Số transaction/statement ghi mỗi giây, số hàng cập nhật |
| Latency | p50/p95/p99 của thao tác ghi và thời gian chờ lock |
| Skew | Tỷ lệ request vào top key, phân phối request theo tenant/product/account |
| Lock | Wait count, wait duration, deadlock, timeout và lock escalation |
| Transaction | Thời gian transaction, số statement, số hàng bị khóa |
| Storage | Log write latency, IOPS, page/index contention và checkpoint pressure |

Nên lấy mẫu theo business key hoặc partition khi hệ quản trị cho phép. Trung bình toàn bảng có thể che giấu một key nóng: 99% sản phẩm gần như không có ghi, nhưng một sản phẩm duy nhất nhận 70% traffic.

## 3. Bất biến nghiệp vụ quyết định giới hạn phân chia

Trước khi chọn kỹ thuật, hãy viết bất biến thành điều kiện có thể kiểm tra.

Ví dụ:

- Tồn kho của một sản phẩm không được âm: `quantity >= 0`.
- Tổng số chỗ đã đặt của một phòng không vượt sức chứa: `SUM(reservation) <= capacity`.
- Số dư tài khoản không được âm: `balance >= 0`.
- Một mã coupon chỉ được sử dụng tối đa 100 lần: `used_count <= 100`.
- Một email chỉ thuộc về một tài khoản: `UNIQUE(email)`.
- Tổng ngân sách đã phân bổ không vượt ngân sách được duyệt.

Phạm vi bất biến có thể là:

1. **Một hàng:** có thể dùng CHECK và UPDATE có điều kiện.
2. **Một khóa nghiệp vụ:** có thể dùng PRIMARY KEY/UNIQUE hoặc một registry duy nhất.
3. **Một nhóm hàng có guard chung:** có thể khóa hàng đại diện hoặc cập nhật bộ đếm tổng hợp.
4. **Nhiều partition/shard:** cần quota được phân bổ, distributed transaction, coordination service hoặc chấp nhận consistency yếu hơn.
5. **Toàn hệ thống:** cần một cơ chế toàn cục, hoặc thay đổi định nghĩa nghiệp vụ để bất biến được phân rã thành những giới hạn cục bộ.

Một kỹ thuật phân chia chỉ an toàn nếu nó bảo toàn bất biến. Nếu không thể chứng minh điều đó, việc tăng throughput có thể đổi lấy lỗi nghiệp vụ như bán vượt tồn kho, vượt sức chứa, dùng coupon quá số lần hoặc chi tiêu vượt ngân sách.

## 4. Ví dụ gốc: một hàng tồn kho nóng

Giả sử sản phẩm 42 có 100 đơn vị tồn kho:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity   INTEGER NOT NULL CHECK (quantity >= 0),
    version    BIGINT NOT NULL DEFAULT 0
);
```

Mỗi đơn hàng muốn lấy một đơn vị:

```sql
UPDATE inventory
SET quantity = quantity - 1,
    version = version + 1
WHERE product_id = 42
  AND quantity >= 1;
```

Kiểm tra số hàng cập nhật: đúng một hàng nghĩa là giữ được một đơn vị; không có hàng nào nghĩa là hết tồn hoặc sản phẩm không tồn tại. Câu lệnh là nguyên tử và `CHECK` là lớp bảo vệ bổ sung.

Ưu điểm của một hàng tổng hợp là bất biến đơn giản, dễ hiểu và dễ kiểm chứng. Nhược điểm là mọi request cho sản phẩm 42 đều cần cập nhật cùng một hàng. Nếu lượng ghi quá lớn, hàng đó trở thành điểm nóng.

Không nên bỏ điều kiện `quantity >= 1` rồi đọc số lượng trước bằng SELECT. Hai transaction có thể cùng đọc 1 và cùng trừ, nếu câu UPDATE không có điều kiện hoặc cơ chế khóa thích hợp thì có nguy cơ vượt giới hạn.

## 5. Phân chia theo khóa nghiệp vụ (partition by key)

Kỹ thuật đơn giản nhất là phân vùng dữ liệu theo một khóa mà các transaction thường chỉ tác động đến một giá trị.

Ví dụ, thay vì một counter toàn hệ thống:

```text
global_counter
```

có thể lưu counter theo tenant:

```text
tenant_counter(tenant_id, count)
```

Mỗi tenant có một hàng riêng. Các request của tenant A không cần cập nhật hàng của tenant B. Nếu bất biến chỉ yêu cầu mỗi tenant có giới hạn riêng, đây là phân chia tự nhiên và không làm mất khả năng kiểm tra cục bộ.

Ví dụ:

```sql
CREATE TABLE tenant_usage (
    tenant_id BIGINT PRIMARY KEY,
    used_bytes BIGINT NOT NULL DEFAULT 0,
    quota_bytes BIGINT NOT NULL,
    CHECK (used_bytes >= 0 AND used_bytes <= quota_bytes)
);

UPDATE tenant_usage
SET used_bytes = used_bytes + :delta
WHERE tenant_id = :tenant_id
  AND used_bytes + :delta <= quota_bytes;
```

Các tenant khác nhau cập nhật các hàng khác nhau. Tuy nhiên, nếu có một quota toàn hệ thống bên cạnh quota từng tenant, bất biến toàn hệ thống vẫn cần được bảo vệ ở một điểm khác.

### Chọn partition key

Một partition key tốt nên:

- Phân phối workload đủ đều.
- Gần với phạm vi bất biến nghiệp vụ.
- Có mặt trong các truy vấn và đường ghi quan trọng.
- Ít thay đổi sau khi tạo dữ liệu.
- Không tạo một partition quá nóng do tenant/product lớn bất thường.

Chọn `tenant_id` có thể hiệu quả nếu traffic phân bố đều giữa tenant. Nhưng một tenant rất lớn có thể vẫn là hot partition. Chọn hash của ID giúp phân phối đều hơn, nhưng truy vấn theo tenant hoặc nghiệp vụ tổng hợp có thể phải fan-out qua nhiều partition.

## 6. Sharding hoặc hash partitioning: tăng điểm ghi, tăng chi phí tổng hợp

Sharding chia dữ liệu thành nhiều vùng lưu trữ hoặc nhiều node. Hash partitioning có thể phân tán các khóa đều hơn:

```text
shard = hash(product_id) mod N
```

Các sản phẩm khác nhau có thể được ghi trên các shard khác nhau. Điều này tăng khả năng song song nếu workload phân bố đều và mỗi transaction chỉ cần một shard.

Nhưng sharding không tự chia một hot key. Nếu 80% request đều cập nhật `product_id = 42`, hash của ID 42 vẫn đưa tất cả request đến cùng shard. Muốn chia chính hot key đó, cần một bucket/subkey bổ sung, ví dụ:

```text
shard = hash(product_id, bucket_id) mod N
```

Việc thêm bucket làm thay đổi phạm vi dữ liệu và thường khiến phép tổng hợp hoặc bảo vệ giới hạn khó hơn.

### Đánh đổi khi sharding

| Lợi ích | Chi phí |
| --- | --- |
| Tăng khả năng ghi song song giữa shard | Truy vấn tổng hợp phải fan-out hoặc đọc dữ liệu tổng hợp |
| Giảm lock contention giữa các khóa khác nhau | Transaction nhiều shard cần coordination hoặc distributed transaction |
| Có thể mở rộng dung lượng theo node | Rebalancing, routing, migration và vận hành phức tạp hơn |
| Cô lập workload theo tenant/key | Hot tenant/key vẫn có thể làm một shard quá tải |
| Giảm áp lực lên một index/node | Unique constraint toàn cục khó bảo đảm nếu khóa nằm ở nhiều shard |

Sharding hiệu quả nhất khi transaction và bất biến có thể được đặt trong một shard. Nếu mọi thao tác vẫn cần một global counter hoặc global uniqueness check, điểm nóng chỉ bị chuyển sang một dịch vụ điều phối khác.

## 7. Bucketed counter: chia một bộ đếm thành nhiều hàng

Với counter phục vụ thống kê, có thể chia một bộ đếm thành nhiều bucket:

```sql
CREATE TABLE product_view_counter (
    product_id BIGINT NOT NULL,
    bucket_id  INTEGER NOT NULL,
    view_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, bucket_id),
    CHECK (view_count >= 0)
);
```

Ứng dụng chọn bucket theo request, thread hash hoặc số ngẫu nhiên:

```sql
UPDATE product_view_counter
SET view_count = view_count + 1
WHERE product_id = :product_id
  AND bucket_id = :bucket_id;
```

Thay vì mọi request cập nhật một hàng, request được phân tán lên N hàng. Tổng lượt xem là:

```sql
SELECT COALESCE(SUM(view_count), 0)
FROM product_view_counter
WHERE product_id = :product_id;
```

### Khi bucketed counter phù hợp

Kỹ thuật này phù hợp với số liệu có tính cộng dồn và chấp nhận tổng được đọc bằng phép SUM, ví dụ:

- Lượt xem sản phẩm.
- Số lần click.
- Số event được xử lý.
- Bộ đếm telemetry hoặc metric.
- Số lần một tác vụ được gọi, khi không dùng để cấp phát giới hạn.

Nó giảm tranh chấp ghi nếu bucket được phân phối đều. Tuy nhiên, đọc tổng phải quét nhiều hàng hoặc dùng một bản tổng hợp được cập nhật định kỳ. Nếu N quá lớn, truy vấn tổng hợp cũng tốn CPU/I/O.

### Vì sao bucketed counter không tự bảo vệ quota?

Giả sử coupon còn 5 lượt và hệ thống chia thành 5 bucket, mỗi bucket cho phép tăng riêng. Nếu mọi bucket đều nghĩ còn lượt, tổng có thể vượt 5. Một CHECK trên từng bucket như `used_count <= 5` chỉ giới hạn từng hàng; nó không giới hạn tổng của 5 hàng.

Bucketed counter chỉ là cách phân tán phép ghi. Nó không tự bảo đảm bất biến tổng. Nếu counter tham gia quyết định “còn bao nhiêu quyền được dùng?”, cần cơ chế phân bổ quota hoặc điều phối khác.

## 8. Escrow/quota allocation: phân chia quyền sử dụng thay vì chỉ phân chia bộ đếm

Escrow là một kỹ thuật phân phối trước một phần quyền sử dụng tài nguyên cho nhiều bucket/partition. Mỗi partition có thể tự thực hiện thao tác trong giới hạn quota được giao mà không cần hỏi một global counter ở mỗi request.

Ví dụ tổng tồn kho là 100. Hệ thống phân bổ quyền bán:

| Bucket | Quota được cấp |
| --- | ---: |
| A | 25 |
| B | 25 |
| C | 25 |
| D | 25 |
| **Tổng** | **100** |

Mỗi bucket có thể bán trong phạm vi quota của mình. Bất biến được bảo vệ bởi:

```text
quota_A + quota_B + quota_C + quota_D <= 100
sold_i <= quota_i  với mọi bucket i
```

Vì tổng quota không vượt 100 và từng bucket không thể bán quá quota của nó, tổng số bán không thể vượt 100:

```text
SUM(sold_i) <= SUM(quota_i) <= 100
```

Đây là cách biến một bất biến toàn cục thành nhiều giới hạn cục bộ có thể kiểm tra độc lập.

### Cấp quota và sử dụng quota

Một schema đơn giản:

```sql
CREATE TABLE inventory_quota (
    product_id BIGINT NOT NULL,
    bucket_id  INTEGER NOT NULL,
    quota      INTEGER NOT NULL,
    sold       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, bucket_id),
    CHECK (quota >= 0),
    CHECK (sold >= 0 AND sold <= quota)
);
```

Mỗi request bán hàng chỉ cập nhật bucket được định tuyến:

```sql
UPDATE inventory_quota
SET sold = sold + :requested
WHERE product_id = :product_id
  AND bucket_id = :bucket_id
  AND sold + :requested <= quota;
```

Nếu cập nhật đúng một hàng, quota của bucket còn đủ. Nếu không, bucket đã hết quyền bán; hệ thống có thể thử bucket khác hoặc yêu cầu tái phân bổ.

### Chuyển quota giữa bucket

Nếu bucket A hết quota trong khi B còn dư, có thể chuyển quyền từ B sang A. Việc chuyển cần bảo đảm tổng quota không tăng:

```text
BEGIN
  khóa quota B và A theo thứ tự khóa ổn định
  xác nhận quota_B - sold_B >= transfer_amount
  quota_B = quota_B - transfer_amount
  quota_A = quota_A + transfer_amount
COMMIT
```

Hai cập nhật phải cùng transaction. Nếu quota nằm ở các shard khác nhau, cần distributed transaction hoặc một quy trình transfer có trạng thái và idempotency để không tạo hoặc mất quota khi lỗi mạng.

### Ưu điểm và chi phí của escrow

- **Ưu điểm:** request thường ngày chỉ ghi một bucket; bất biến tổng được bảo vệ bằng tổng quota đã cấp.
- **Chi phí:** quota có thể bị mắc kẹt ở bucket ít traffic trong khi bucket nóng hết quyền sử dụng; cần quy trình chuyển quota.
- **Độ trễ:** thao tác bình thường nhanh, nhưng khi cần tái phân bổ có thể phải coordination.
- **Độ phức tạp:** phải xử lý crash trong lúc chuyển quota, retry, bucket mất kết nối và đối soát tổng quota.

Escrow phù hợp khi tài nguyên có thể chia thành quyền sử dụng hữu hạn và hệ thống chấp nhận phân bổ quota trước. Ví dụ tồn kho, coupon, hạn mức tín dụng hoặc số chỗ đặt. Không phù hợp nếu không thể chia quyền hoặc mỗi đơn vị tài nguyên cần một quyết định toàn cục tức thời.

## 9. Guard row: giữ một điểm điều phối có chủ đích

Không phải lúc nào cũng nên chia nhỏ điểm ghi. Nếu một bất biến nhiều hàng phải được kiểm tra ngay trên tổng, một hàng guard có thể là lựa chọn đơn giản và an toàn.

Ví dụ mỗi phòng có một hàng `room_capacity`. Mọi transaction đặt chỗ đều cập nhật hàng đó trước khi chèn reservation. Guard row tuần tự hóa các thao tác cho cùng phòng nhưng các phòng khác nhau vẫn chạy song song.

```sql
UPDATE room_capacity
SET reserved_count = reserved_count + :guests
WHERE room_id = :room_id
  AND reserved_count + :guests <= capacity;
```

Nếu một hàng guard cho toàn hệ thống, tất cả tenant tranh chấp cùng hàng. Hãy phân rã guard theo phạm vi bất biến nhỏ nhất có thể: theo account, room, warehouse, tenant hoặc campaign. Khi đó các nhóm độc lập không cần chờ nhau.

Guard row là một điểm tranh chấp có chủ đích. Nó thường đáng giữ nếu bất biến cần quyết định tức thời và việc chia quota phức tạp hơn chi phí lock hiện tại.

## 10. Shard theo phạm vi bất biến, không chỉ theo phân phối dữ liệu

Một partition key tốt không chỉ làm dữ liệu phân bố đều; nó còn giúp các transaction bảo vệ bất biến trong một phạm vi cục bộ.

Ví dụ hệ thống đặt phòng có thể phân vùng theo `room_id`. Mọi reservation và capacity của cùng một phòng nằm trên cùng partition. Transaction đặt phòng chỉ cần điều phối trong partition đó. Phòng 1 và phòng 2 không tranh chấp guard của nhau.

Ngược lại, nếu phân vùng theo `reservation_id`, các reservation của cùng một phòng có thể nằm ở nhiều shard. Khi kiểm tra tổng sức chứa, transaction phải truy vấn nhiều shard hoặc dùng một bộ đếm toàn cục. Cách phân vùng theo reservation ID có thể cân bằng lưu trữ nhưng làm bất biến theo room khó bảo vệ hơn.

Hãy chọn partition key dựa trên:

1. Đối tượng mà nghiệp vụ cần bảo vệ bất biến.
2. Các thao tác thường cùng nằm trong một transaction.
3. Phân phối tải giữa các đối tượng đó.
4. Khả năng một đối tượng đơn lẻ trở thành hot key.
5. Nhu cầu truy vấn và báo cáo xuyên partition.

Nếu một đối tượng quá nóng, có thể kết hợp partition theo đối tượng với bucket/escrow bên trong đối tượng đó.

## 11. Per-key serial queue hoặc actor: tuần tự hóa trong phạm vi một khóa

Một cách khác để giảm lock contention là đưa các lệnh thay đổi cùng business key vào một hàng đợi tuần tự, trong khi các key khác được xử lý song song.

Ví dụ:

```text
Queue account-100:  debit -> credit -> fee -> adjustment
Queue account-200:  credit -> debit -> refund
Queue account-300:  debit -> fee
```

Mỗi account có một actor/worker xử lý lần lượt các command của nó. Các account khác nhau vẫn chạy song song. Đây là mô hình hữu ích cho aggregate có bất biến cục bộ, chẳng hạn trạng thái đơn hàng hoặc số dư theo tài khoản.

### Điều cần chú ý

- Queue phải bền vững hoặc có cơ chế phục hồi nếu process chết.
- Command cần ID duy nhất để deduplicate khi broker gửi lại.
- Nếu một transaction thay đổi hai account, cần phối hợp hai key; không thể đơn giản gửi một command vào hai queue rồi giả định nguyên tử.
- Thứ tự message trong partition/queue phải phù hợp với thứ tự nghiệp vụ.
- Một key nóng vẫn chỉ có một luồng xử lý tuần tự; queue không làm tăng song song cho cùng key.

Per-key serial queue chuyển tranh chấp từ database lock sang cơ chế điều phối command. Nó hữu ích khi muốn kiểm soát thứ tự và hấp thụ burst, nhưng cần thiết kế delivery, retry, idempotency và multi-key operation.

## 12. Unique constraint và bất biến khi chia shard

Một unique constraint trong database thường chỉ bảo đảm uniqueness trong phạm vi index/database mà nó quản lý. Khi dữ liệu được chia sang nhiều shard độc lập, hai shard có thể cùng chấp nhận một giá trị nếu không có registry toàn cục.

Ví dụ email phải duy nhất:

```text
Shard A: INSERT email = user@example.com -> thành công
Shard B: INSERT email = user@example.com -> thành công
```

Nếu hai shard không chia sẻ unique index, bất biến đã bị phá vỡ.

Các cách xử lý thường gặp:

- **Định tuyến theo khóa unique:** hash email đã chuẩn hóa để mọi bản ghi cùng email luôn đến một shard.
- **Global uniqueness registry:** một bảng/dịch vụ trung tâm giữ quyền sở hữu khóa trước khi ghi entity.
- **Distributed transaction:** ghi registry và entity atomically nếu hạ tầng hỗ trợ XA/2PC phù hợp.
- **Reservation/claim protocol:** tạo claim có trạng thái, lease và idempotency; xử lý phục hồi nếu một bước thất bại.
- **Định danh toàn cục:** dùng UUID/ULID giảm xác suất va chạm, nhưng không thay thế unique constraint nếu nghiệp vụ yêu cầu tuyệt đối không trùng.

Một UUID ngẫu nhiên gần như không trùng trong thực tế nhưng không chứng minh được uniqueness của email, username hoặc mã nghiệp vụ do người dùng chọn.

## 13. Chuyển từ một counter sang nhiều bucket mà vẫn giữ đúng

Giả sử tồn kho ban đầu là 100. Có thể chuyển qua các giai đoạn:

### Giai đoạn 1: một hàng authoritative

Mọi thao tác bán cập nhật một hàng `inventory`. Đây là mô hình đơn giản nhất, dễ audit và kiểm tra.

### Giai đoạn 2: đo điểm nóng

Xác định sản phẩm nào có contention cao, thời gian lock wait và phân phối request. Chỉ chọn sản phẩm nóng để thử nghiệm phân chia.

### Giai đoạn 3: phân bổ quota

Tạo bucket và cấp quota sao cho tổng quota không vượt tồn kho thực tế. Ví dụ 4 bucket mỗi bucket 25.

### Giai đoạn 4: chuyển luồng ghi

Mỗi request được định tuyến đến bucket và chỉ được bán trong quota. Transaction ghi sale/ledger và tăng sold trong cùng transaction cục bộ.

### Giai đoạn 5: chuyển quota có kiểm soát

Khi bucket cạn, chuyển quota từ bucket dư theo một transaction có khóa/coordination. Ghi transfer ID duy nhất để retry không chuyển quota hai lần.

### Giai đoạn 6: đối soát

Định kỳ kiểm tra:

```text
SUM(quota) <= authoritative_stock
SUM(sold) = tổng số lượng bán đã ghi nhận
SUM(quota - sold) = quyền bán còn lại
```

Nếu có hàng hoàn trả, hủy đơn hoặc điều chỉnh tồn kho, quy tắc hoàn quota phải được định nghĩa rõ. Không thể chỉ cộng lại quota khi refund nếu đơn hàng chưa thực sự được hủy hoặc sản phẩm chưa đủ điều kiện bán lại.

## 14. Bất biến toàn cục và coordination cost

Một bất biến toàn cục có thể khiến hệ thống phải phối hợp nhiều partition. Ví dụ “tổng tiền rút từ mọi tài khoản không vượt ngân sách 1 tỷ” hoặc “tối đa 1.000 voucher được phát trên toàn chiến dịch”. Nếu mỗi partition tự kiểm tra một snapshot cục bộ, tổng toàn hệ thống có thể vượt giới hạn.

Có một số hướng lựa chọn:

1. **Giữ một điểm điều phối toàn cục:** dễ chứng minh, nhưng có thể là bottleneck.
2. **Phân bổ quota/escrow:** giảm coordination trên mỗi request; cần chuyển quota và đối soát.
3. **Distributed transaction:** giữ atomicity xuyên nhiều resource; tăng latency và độ phức tạp recovery.
4. **Eventual consistency + reconciliation:** cho phép trạng thái tạm thời lệch; chỉ phù hợp khi nghiệp vụ chấp nhận và có cách bù trừ.
5. **Thay đổi mô hình nghiệp vụ:** chia giới hạn theo tenant/region/partition nếu business cho phép thay vì yêu cầu một global limit tức thời.

Không có kỹ thuật nào vừa loại bỏ coordination hoàn toàn vừa bảo đảm mọi bất biến toàn cục tức thời trong mọi tình huống phân tán. Nếu một quyết định cần biết tổng chính xác tại đúng thời điểm commit, hệ thống phải có một cơ chế đồng bộ hóa tương ứng.

## 15. Eventual consistency và reconciliation

Một số dữ liệu có thể được cập nhật bất đồng bộ. Ví dụ lượt xem, số liệu analytics hoặc số lượng dashboard. Trong các trường hợp đó, hệ thống có thể chấp nhận counter tổng hợp trễ vài giây.

Tuy nhiên, cần phân biệt:

- **Metric chỉ để quan sát:** tổng có thể trễ mà không ảnh hưởng quyền thực hiện nghiệp vụ.
- **Counter dùng để ra quyết định:** tổng trễ có thể làm vượt quota hoặc bán quá tồn kho.

Nếu chấp nhận eventual consistency, cần xác định:

- Mức trễ tối đa có thể chấp nhận.
- Dữ liệu authoritative nằm ở đâu.
- Cách deduplicate event.
- Cách xử lý event đến sai thứ tự.
- Cách phục hồi khi consumer dừng.
- Cách đối soát và sửa sai.
- Có cho phép trạng thái vượt giới hạn tạm thời hay không.

Reconciliation không thay thế kiểm soát đồng thời nếu vượt giới hạn gây hậu quả không thể đảo ngược. Đối soát phát hiện và sửa sai sau đó không thể hoàn tác một vé đã dùng, một khoản tín dụng đã giải ngân hoặc một chỗ đặt đã cam kết với khách hàng.

## 16. Chọn kỹ thuật theo loại dữ liệu

| Loại dữ liệu/định luật | Kỹ thuật thường phù hợp | Lý do |
| --- | --- | --- |
| Lượt xem, click, telemetry | Bucketed counter, queue/stream aggregation | Có thể cộng dồn và chấp nhận tổng trễ |
| Tồn kho hữu hạn | Guard row, atomic conditional update hoặc escrow quota | Không được bán vượt lượng có sẵn |
| Số chỗ đặt theo phòng | Guard theo room hoặc quota theo bucket có giới hạn | Bất biến gắn với một phòng; có thể phân chia theo phòng |
| Số dư tài khoản | Một aggregate/guard theo account, per-key serialization | Mọi thay đổi số dư cần được tuần tự hóa theo tài khoản |
| Coupon giới hạn toàn chiến dịch | Escrow quota theo partition hoặc global coordinator | Tổng lượt dùng phải nằm trong giới hạn |
| Username/email unique | Unique index/registry và routing theo giá trị unique | Cần quyết định duy nhất có thẩm quyền |
| Trạng thái đơn hàng | Partition/actor theo order ID | Các chuyển trạng thái của cùng đơn cần có thứ tự |
| Ngân sách toàn tổ chức | Quota theo bộ phận hoặc global coordination | Cần bảo toàn tổng hạn mức |

## 17. Đánh đổi về throughput, latency và độ chính xác

Phân chia điểm ghi thường cải thiện throughput nhưng có thể làm các thao tác tổng hợp và điều phối phức tạp hơn.

| Thiết kế | Throughput ghi | Độ trễ ghi | Độ chính xác của bất biến | Độ phức tạp vận hành |
| --- | --- | --- | --- | --- |
| Một hàng authoritative | Thấp hơn khi key nóng | Có thể tăng do lock wait | Dễ bảo đảm bằng atomic update/constraint | Thấp |
| Nhiều bucket counter | Cao hơn cho phép cộng dồn | Thấp hơn nếu phân phối đều | Không tự bảo đảm giới hạn tổng | Trung bình |
| Guard theo aggregate | Cao giữa các aggregate; tuần tự trong từng aggregate | Chờ trong cùng aggregate | Cao nếu mọi đường ghi dùng guard | Thấp đến trung bình |
| Escrow/quota | Cao trong phạm vi quota cục bộ | Thấp khi quota còn; tăng khi tái phân bổ | Có thể bảo đảm tổng nếu invariant quota đúng | Cao |
| Per-key queue/actor | Cao giữa key; tuần tự cùng key | Có thể tăng do queue backlog | Cao nếu mọi command đi qua đúng owner | Trung bình đến cao |
| Eventual consistency | Cao cho ingest | Ghi nhanh, tổng hợp trễ | Có thể tạm thời vi phạm nếu không có quota | Cao |
| Distributed transaction | Bị giới hạn bởi coordination và network | Thường cao hơn | Atomicity xuyên resource nếu cấu hình đúng | Cao |

Các đánh giá trên là xu hướng, không phải benchmark tuyệt đối. Kết quả thực tế phụ thuộc database, index, isolation level, network, batch size và phân phối key.

## 18. Một quy trình thiết kế và triển khai

1. **Viết bất biến:** mô tả điều kiện bằng biểu thức và xác định thời điểm phải luôn đúng.
2. **Xác định phạm vi:** một hàng, một aggregate, một tenant, một partition hay toàn hệ thống.
3. **Đo điểm nóng:** tìm key, index hoặc resource có lock wait cao và workload skew.
4. **Tách nguyên nhân:** xác nhận bottleneck là contention chứ không phải I/O, log flush hoặc transaction dài.
5. **Chọn mức phân chia nhỏ nhất:** partition theo business key trước; chỉ bucket hóa một hot key khi cần.
6. **Chọn cơ chế bảo vệ:** constraint, conditional update, guard, version, escrow hoặc serializable/distributed coordination.
7. **Chứng minh invariant:** viết bất đẳng thức hoặc lập luận cho thấy mọi transaction hợp lệ không thể vượt giới hạn.
8. **Thiết kế retry/idempotency:** xử lý deadlock, timeout, duplicate message và lỗi giữa các bước chuyển quota.
9. **Triển khai có thể rollback:** bắt đầu với một nhóm key/tenant và so sánh metric trước/sau.
10. **Đối soát:** so sánh bucket, quota, ledger và nguồn authoritative.
11. **Theo dõi:** lock wait, bucket skew, quota exhaustion, reallocation latency, duplicate và invariant violation.

## 19. Kiểm thử concurrency cho thiết kế phân chia

Kiểm thử cần tạo nhiều connection hoặc worker thực sự đồng thời. Một vòng lặp tuần tự không thể chứng minh rằng điểm tranh chấp đã được phân phối đúng hoặc bất biến vẫn được giữ.

### Kiểm thử bucketed counter

1. Khởi tạo N bucket cho một product.
2. Gửi nhiều request tăng counter đồng thời, chọn bucket theo thuật toán routing.
3. Xác nhận các bucket nhận tải tương đối phân tán.
4. Đọc tổng bằng SUM và so với số request đã xác nhận.
5. Kiểm tra retry cùng event ID không tăng counter hai lần.

### Kiểm thử escrow quota

1. Cấp tổng quota bằng tồn kho authoritative.
2. Gửi request bán đồng thời vào mọi bucket.
3. Cố tình làm một bucket hết quota trong khi bucket khác còn dư.
4. Chạy transfer quota đồng thời với các request bán.
5. Tiêm lỗi trước/sau commit khi chuyển quota rồi retry cùng transfer ID.
6. Xác nhận `SUM(quota) <= stock` và `sold_i <= quota_i` luôn đúng.
7. Xác nhận tổng số bán không vượt stock.

### Kiểm thử guard row

1. Gửi nhiều request đặt cùng một room.
2. Gửi request vào nhiều room khác nhau.
3. Xác nhận request cùng room được điều phối, còn room khác có thể chạy song song.
4. Tạo một luồng ghi cố tình bỏ qua guard trong môi trường test để chứng minh test phát hiện vi phạm.

### Kiểm thử partition và unique key

1. Gửi cùng một email đến hai node định tuyến đồng thời.
2. Xác nhận cả hai request đi đến cùng registry/shard hoặc có global uniqueness coordination.
3. Tiêm lỗi giữa bước claim key và ghi entity.
4. Retry cùng key và xác nhận không có duplicate hoặc claim mồ côi không thể phục hồi.

### Kiểm thử workload skew

Tạo workload có phân phối đều và workload có một hot key chiếm phần lớn request. So sánh throughput, p95/p99 latency, lock wait, queue backlog và phân phối bucket. Một thiết kế có thể tốt ở phân phối đều nhưng vẫn tắc khi một key nóng chiếm 80% traffic.

## 20. Những sai lầm thường gặp

- **Chia counter rồi cho rằng bất biến tự được giữ:** `SUM(bucket)` không có atomicity nếu các writer cập nhật độc lập.
- **Dùng random bucket nhưng không đo skew:** phân phối ngẫu nhiên có thể vẫn tạo bucket nóng, đặc biệt với ít bucket hoặc workload lệch.
- **Chọn partition key không khớp với aggregate:** truy vấn và invariant phải fan-out qua nhiều shard.
- **Dùng một global coordinator cho mọi request:** đã phân chia dữ liệu nhưng vẫn giữ một điểm nóng duy nhất ở coordinator.
- **Chuyển quota không nguyên tử:** crash có thể làm quota bị nhân đôi hoặc biến mất.
- **Dùng eventual consistency cho giới hạn không thể vượt:** reconciliation phát hiện sai sau khi hậu quả đã xảy ra.
- **Dựa vào cache hoặc số liệu analytics để quyết định quyền bán:** dữ liệu có thể stale hoặc được cập nhật bất đồng bộ.
- **Retry mà không có idempotency:** cùng request có thể tăng counter, chuyển quota hoặc ghi ledger nhiều lần.
- **Bỏ qua hot tenant:** hash partitioning đều theo số key không có nghĩa đều theo lượng traffic.
- **Chỉ benchmark throughput:** p99 latency, lock wait, reallocation và khả năng phục hồi cũng quyết định chất lượng thiết kế.

## 21. Những điểm cần ghi nhớ

- Điểm tranh chấp là hàng, khóa, index hoặc tài nguyên mà nhiều transaction cần cập nhật theo cách xung đột.
- Chỉ phân chia sau khi đo được hot key và xác định đúng bottleneck.
- Bất biến nghiệp vụ quyết định mức độ có thể phân chia; hãy xác định nó thuộc một hàng, aggregate, partition hay toàn hệ thống.
- Partition theo business key giúp các aggregate độc lập chạy song song và giữ invariant trong phạm vi cục bộ.
- Bucketed counter tăng throughput cho metric cộng dồn, nhưng phép SUM nhiều bucket không tự bảo vệ quota tổng.
- Escrow/quota allocation chia trước quyền sử dụng sao cho tổng quota không vượt tài nguyên authoritative; mỗi bucket chỉ dùng trong quota của mình.
- Chuyển quota cần transaction/coordination, ID idempotent và đối soát để không nhân đôi hoặc làm mất quyền sử dụng.
- Guard row giữ một điểm điều phối có chủ đích; có thể phân rã guard theo room, account, tenant hoặc aggregate để giảm tranh chấp giữa các nhóm độc lập.
- Sharding chỉ giúp một hot key nếu chính hot key đó được chia thêm bucket/subkey; hash của cùng một ID vẫn đi về cùng shard.
- Unique constraint thường chỉ có hiệu lực trong phạm vi index/database; uniqueness toàn shard cần routing theo key, registry hoặc coordination toàn cục.
- Per-key queue/actor tuần tự hóa command trong một aggregate và cho phép key khác chạy song song; queue cần durability, idempotency và xử lý thao tác nhiều key.
- Eventual consistency phù hợp với metric và dữ liệu cho phép trễ; không phù hợp với giới hạn cứng nếu vượt giới hạn gây hậu quả không thể bù trừ.
- Đánh giá thiết kế bằng cả throughput, p95/p99 latency, lock wait, quota exhaustion, reallocation, skew và khả năng phục hồi.
