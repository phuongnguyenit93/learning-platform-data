# Phân hoạch theo băm khi dữ liệu không vừa bộ nhớ

**Phân hoạch theo băm** (*hash partitioning*) là kỹ thuật chia một tập bản ghi rất lớn thành các **phân vùng nhỏ** dựa trên khóa. Khi toàn bộ dữ liệu không thể nằm trong RAM, thuật toán đọc đầu vào theo **khối**, dùng một hàm băm để đưa các bản ghi vào **bộ đệm đầu ra** của từng phân vùng, ghi những bộ đệm đầy xuống các tệp/phân vùng trên đĩa, rồi lần lượt xử lý từng phân vùng. Ý tưởng cốt lõi là: **hai bản ghi có cùng khóa phải được đưa về cùng phân vùng**, nhờ vậy nhiều phép toán theo khóa có thể thực hiện trên các tập con thay vì giữ toàn bộ dữ liệu trong bộ nhớ cùng lúc.

Bài thuộc chủ đề **Ngoài bộ nhớ** (*external-memory / out-of-core algorithms*). Hai ứng dụng quan trọng là **gom nhóm/đếm theo khóa** (*external hash aggregation / GROUP BY*) và **phép nối theo khóa bằng băm** (*Grace hash join*). Một phiên bản tốt cần nắm cả **bộ nhớ `M`**, **kích thước khối `B`**, **số phân vùng `F`**, **chi phí đọc–ghi** và **khi nào phải phân hoạch lại hoặc đổi thuật toán vì phân vùng quá lớn**.

Đây **không** phải lời hứa rằng sau đúng một lượt chia, mọi phân vùng chắc chắn vừa RAM. Sự phân phối khóa, khóa lặp lại rất nhiều (*skew/heavy hitter*), hàm băm và ngân sách bộ đệm có thể khiến một phân vùng lớn hơn dự kiến. Kỹ thuật đúng phải **phát hiện** điều đó và có phương án tiếp tục, chẳng hạn repartition với hàm băm mới, xử lý khóa nặng riêng hoặc chuyển sang sắp xếp ngoài bộ nhớ.

Bài có ví dụ từng khối, chứng minh bất biến, phân tích I/O, các tình huống phản ví dụ, chương trình **Java 17+ độc lập** mô phỏng thiết bị khối và gộp/joins. Mã đối chiếu chính xác với `TreeMap` và phép nested-loop, kiểm thử ngẫu nhiên và phát hiện phân vùng vượt ngân sách thay vì giả vờ giải được.

## 1. Mô hình dữ liệu và hai tầng bộ nhớ

Ta dùng mô hình I/O hai tầng:

```text
N = số bản ghi đầu vào.
M = số bản ghi tối đa có thể chứa trong RAM dùng cho thuật toán.
B = số bản ghi cố định chứa trong một khối truyền dữ liệu.
F = số phân vùng đầu ra được mở trong một lượt partition.
```

Thường:

```text
N >> M >= B.
```

Một lần truyền khối `readBlock` đọc tối đa B bản ghi liên tiếp từ ngoài bộ nhớ vào RAM; `writeBlock` ghi một khối từ RAM xuống thiết bị/tệp. Trong mô hình đơn giản, **chi phí I/O = số lượt đọc khối + số lượt ghi khối**. Một lệnh xử lý record trong RAM không trực tiếp được tính là I/O.

**Nếu record có kích thước biến đổi**, hãy quy đổi các dung lượng sang byte và tính số record trung bình hoặc dùng bố trí page thực. Ký hiệu M/B dưới đây giả định record kích thước cố định và metadata đã được cấp ngân sách hợp lý.

### 1.1. Vì sao hash map thông thường chưa đủ?

Để tính:

```text
SELECT key, SUM(value)
FROM huge_table
GROUP BY key;
```

cách trong RAM là:

```text
Map<Key,Long> sums
for each record:
    sums[key] += value
```

Nếu có quá nhiều **khóa phân biệt**, toàn bộ hash table không vừa RAM. Để thực hiện phép equi-join:

```text
SELECT ...
FROM R JOIN S ON R.key = S.key;
```

một hash join trong RAM thường cần giữ phía build (ví dụ R) trong RAM. Nếu R lớn hơn M, việc build một bảng băm duy nhất có thể không khả thi. Cả hai trường hợp đều cần cách tổ chức I/O theo **phân vùng khóa**.

### 1.2. Không nên nhầm “số bản ghi” với “số khóa phân biệt”

Gom nhóm và join có hai tiêu chí bộ nhớ khác nhau:

- **GROUP BY theo khóa:** sau khi đọc một phân vùng, hash table chỉ cần giữ **một entry cho mỗi khóa phân biệt** cùng tổng tích lũy. Một phân vùng chứa một triệu bản ghi nhưng chỉ một khóa có thể gom với một bộ đếm nhỏ.
- **Hash join tổng quát:** bảng build có thể cần giữ **từng bản ghi phía build**, vì các bản ghi cùng khóa có payload khác nhau và đều tham gia kết quả nối. Một phân vùng với một triệu bản ghi cùng khóa vẫn có thể quá lớn.

Vì vậy “`partition.size > M` thì tất cả thao tác đều không làm được” là kết luận quá mạnh. Điều cần kiểm tra là **cấu trúc dữ liệu cụ thể của pha xử lý** có vừa bộ nhớ hay không.

## 2. Bất biến then chốt: cùng khóa → cùng phân vùng

Chọn một hàm băm xác định `h(key)` và số phân vùng F. Gán:

```text
partition(key) = h(key) mod F
```

hoặc dùng hàm ánh xạ khác vào các số `0,1,...,F−1`.

Mỗi record `(key,payload)` đi vào phân vùng:

```text
P[partition(key)].
```

Điều bắt buộc:

```text
key(a) == key(b)
    => partition(key(a)) == partition(key(b)).
```

Không yêu cầu chiều ngược lại. **Hai khóa khác nhau có thể cùng phân vùng** do va chạm băm; chúng chỉ cần được phân biệt lại ở pha xử lý bên trong phân vùng.

### 2.1. Ví dụ dễ tính tay

Lấy `F=3`, minh họa bằng:

```text
partition(k) = floorMod(k,3)
```

Luồng:

```text
(7,A), (3,B), (4,C), (7,D), (8,E), (3,F),
(10,G), (2,H), (4,I).
```

Kết quả:

| Phân vùng | Các bản ghi theo thứ tự phát ra |
| --- | --- |
| P0 | `(3,B)`, `(3,F)` |
| P1 | `(7,A)`, `(4,C)`, `(7,D)`, `(10,G)`, `(4,I)` |
| P2 | `(8,E)`, `(2,H)` |

Khóa 7 luôn ở P1, khóa 3 luôn ở P0. Các khóa 7,4,10 **cùng P1 dù không bằng nhau**; pha GROUP BY phải kiểm tra khóa thật trong P1, không được coi cả P1 là một nhóm duy nhất.

Trong Java, `%` trên số nguyên âm giữ dấu của số bị chia; `-1 % 3` bằng −1, không phải bucket hợp lệ. Với modulo trực tiếp, dùng `Math.floorMod(key,F)` hoặc một hàm hash đã đưa về dải `[0,F)`.

### 2.2. Phân hoạch không phải sắp xếp

Sau khi partition, các record trong một phân vùng **không nhất thiết sắp xếp theo khóa**. Hash partition chỉ bảo đảm **co-location theo khóa**. Nếu cần kết quả:

```text
ORDER BY key
```

phải sort sau đó hoặc dùng cấu trúc khác. Nếu chỉ cần `SUM(value) GROUP BY key`, hash aggregation trong từng phân vùng có thể đủ. Một phân vùng không có khóa nào được xem là phân vùng rỗng, không cần block ghi đầu ra.

### 2.3. Chất lượng hash quan trọng nhưng không thay đổi correctness

Nếu cùng khóa được ánh xạ nhất quán, kết quả group/join vẫn đúng **kể cả các phân vùng không cân bằng** — miễn hệ thống có cách xử lý phân vùng quá lớn. Hash chất lượng kém có thể dồn hầu hết record vào một phân vùng và làm thuật toán chậm hoặc vượt RAM; đó là vấn đề **tài nguyên/hiệu năng**, không có nghĩa mọi va chạm đều làm kết quả sai.

Với phép join hai đầu vào, dùng **cùng hàm partition** cho cả R và S mới bảo đảm khóa bằng nhau của hai phía được đưa cùng số phân vùng. Nếu dùng seed/salt khác cho hai phía, có thể bỏ sót cặp kết quả.

## 3. Bộ đệm đầu vào và bộ đệm đầu ra

Không nên phát một write nhỏ mỗi khi đọc một record và tính xong hash. Thay vào đó, cấp:

```text
1 input buffer chứa B records
F output buffers, mỗi buffer chứa B records.
```

Bộ nhớ cho những khối này xấp xỉ:

```text
M_buffers = (F+1)*B.
```

Điều kiện khả thi của bố trí cơ bản:

```text
(F+1)*B <= M

=> F <= floor(M/B)-1.
```

Đây là **cận trên lý tưởng chỉ tính các block buffer**. Trong hệ thống thật phải chừa thêm RAM cho hash state, metadata, đối tượng Java, bảng phân vùng, queue, filesystem và các cấu trúc tạm. Vì vậy fan-out thực tế có thể thấp hơn.

### 3.1. Pseudocode một lượt partition

```text
PARTITION(input, F, B, hash):
    allocate one B-record input page
    allocate F output pages of B records
    open/create F logical output partitions

    while an input page exists:
        read next input page from disk

        for each valid record in input page:
            p = hash(record.key) mod F
            append record to outputBuffer[p]

            if outputBuffer[p] contains B records:
                write complete output page to partition[p]
                clear outputBuffer[p]

    for p=0..F-1:
        if outputBuffer[p] is not empty:
            write its final partial page
            clear outputBuffer[p]
```

**Một record được phát đúng một lần** vào một bucket. Các buffer giúp gom B lần ghi record thành một block write, còn page cuối của mỗi partition có thể chưa đầy.

### 3.2. Ví dụ N=20, B=4, M=20, F=4

```text
Input records N=20.
B=4 records/block.
M=20 records.
F=4 partitions.

Input buffer: 4 records.
Output buffers: 4 * 4 = 16 records.
Total buffers = 20 = M.
```

Nếu sau hash, bốn partition chứa lần lượt:

```text
P0 = 4 records
P1 = 4 records
P2 = 2 records
P3 = 10 records.
```

Số input blocks cần đọc:

```text
Q_read = ceil(20/4)=5.
```

Số output blocks cần ghi:

```text
Q_write =
    ceil(4/4) + ceil(4/4) +
    ceil(2/4) + ceil(10/4)

  = 1+1+1+3 = 6.
```

Vậy:

```text
Partition pass = 5 reads + 6 writes = 11 I/Os.
```

Một phân tích vội viết đúng `2*N/B = 10` rồi khẳng định **chính xác 10** I/O sẽ bỏ sót **page cuối chưa đầy**. Theo bậc lớn:

```text
Q_partition = O(N/B + F)
```

với F partition có output page cuối riêng; chính xác hơn, lượt đọc đầu vào là `ceil(N/B)` và số ghi là `SUM_i ceil(N_i/B)`. Nếu các phân vùng đều có dữ liệu và page cuối đầy, số ghi gần `N/B`; nếu rất nhiều phân vùng thưa, phần `+F` không còn bỏ qua được trong tính toán chi tiết.

### 3.3. Tại sao không tạo F quá lớn?

F lớn có thể làm số record mỗi partition nhỏ hơn, nhưng lại cần thêm F output buffers và thêm nhiều page cuối chưa đầy. F quá lớn cũng có thể tạo quá nhiều file/handle, gây chi phí metadata, flush, mở/đóng file và giới hạn hệ điều hành.

**Tối ưu F không chỉ là chọn giá trị lớn nhất**; phải cân bằng RAM, kích thước phân vùng, số pass cần làm, overhead và skew. Một hệ thống có thể partition theo nhiều tầng hoặc dùng số lượng writer đang mở thấp hơn tổng số partition logic, nhưng lúc đó phải tính lại chi phí buffer, eviction và ghi xen kẽ.

## 4. Dự đoán kích thước phân vùng và lý do dễ sai

Nếu khóa được phân phối tương đối đều vào F bucket, kích thước trung bình:

```text
N_i ≈ N/F.
```

Muốn xử lý tiếp từng phân vùng trong RAM với ngân sách thực sự M_work, một lựa chọn sơ bộ là:

```text
N/F <= M_work

=> F >= ceil(N/M_work).
```

Kết hợp điều kiện buffer:

```text
ceil(N/M_work) <= F <= floor(M/B)-1.
```

Nếu không có F thỏa đồng thời, **một lượt phân hoạch chưa đủ** với cấu hình đó: cần **nhiều lượt**, giữ các phân vùng ngoài đĩa và phân hoạch lại những phân vùng quá lớn hoặc dùng một kế hoạch khác.

### 4.1. “Trung bình vừa RAM” không chứng minh “mọi bucket vừa RAM”

Dù `N/F<M_work`, một bucket vẫn có thể chứa lượng dữ liệu vượt M_work. Phân phối đều **trên kỳ vọng** không phải cận chắc chắn cho bucket lớn nhất. Cần xét:

- Phân phối khóa đầu vào;
- Số bản ghi cùng khóa;
- Chất lượng hash và tính độc lập giữa các lượt;
- Sai lệch do modulo;
- Số lượng partition và tail bound nếu muốn cận xác suất;
- Overhead của bảng build/hash aggregation trong RAM.

**Không được tiếp tục build một hash table lớn hơn bộ nhớ chỉ vì công thức N/F dự đoán nhỏ.** Kiểm tra kích thước thực tế từng partition hoặc dùng spill theo giới hạn là bước bắt buộc.

### 4.2. Ví dụ dữ liệu lớn

Cho:

```text
N = 1,000,000 records
M =   100,000 records RAM
B =     1,000 records/block.
```

Số frame trong RAM:

```text
M/B = 100 frames.
```

Bố trí một input page và F output pages cho:

```text
F <= 99.
```

Nếu chọn F=20, kích thước trung bình của một partition dưới giả thiết phân bố đều khoảng:

```text
N/F = 50,000 records.
```

Nếu pha tiếp theo có 80.000 record RAM trống cho bảng build, **trung bình** bucket vừa. Nhưng nếu một khóa nặng có 400.000 bản ghi, bucket chứa khóa đó vẫn có ít nhất 400.000 record và **không thể vừa** bảng build 80.000 record.

Nếu F=99, trung bình chỉ còn khoảng 10.101 record/bucket, nhưng vẫn không làm nhỏ được 400.000 record **cùng khóa**: cùng khóa phải về cùng partition. Đây là giới hạn cấu trúc, không phải lỗi chọn seed thông thường.

## 5. Ứng dụng 1: GROUP BY ngoài bộ nhớ

Cần tính:

```text
SELECT key, SUM(weight)
FROM records
GROUP BY key;
```

Một phương án hai pha:

**Pha partition:**

1. Quét luồng record theo block.
2. Hash theo `key`.
3. Ghi những record có cùng bucket vào cùng file phân vùng.
4. Không cần giữ bảng nhóm của toàn bộ dữ liệu trong RAM.

**Pha aggregate:**

1. Lần lượt mở một phân vùng ở chế độ đọc tuần tự.
2. Tạo một bảng `Map<Key,Sum>` trong RAM chỉ cho phân vùng ấy.
3. Cộng dồn giá trị của từng record.
4. Ghi/stream nhóm kết quả ra output, giải phóng Map rồi sang phân vùng tiếp theo.

### 5.1. Bất biến của kết quả GROUP BY

Với mọi khóa x:

```text
G(x) =
  SUM_{record r in input, r.key=x} r.weight.
```

Hash bảo đảm mọi record có key=x cùng partition P_i. Khi `aggregate(P_i)` duyệt đủ record và cộng đúng, nó tính chính xác G(x). Các partition khác không có key=x nên không góp vào nhóm này. Ghép kết quả của tất cả partition không làm mất/nhân đôi nhóm.

**Phải xử lý va chạm:** Nếu x và y khác nhau nhưng cùng P_i, Map cục bộ vẫn phải dùng **khóa thật**, không chỉ số partition, để giữ hai nhóm khác nhau.

### 5.2. Khi một bucket nhiều record nhưng ít key

Xem:

```text
100,000 records:
  mỗi record có key=5, weight=1.
```

Bucket tương ứng có 100.000 record; nếu `M=20,000`, **toàn bộ bucket không vừa RAM**. Tuy nhiên, GROUP BY `key=5` chỉ cần một bộ đếm:

```text
Map[5]=100000.
```

Ta có thể **stream** qua bucket mà không cần giữ tất cả record. Vì thế điều kiện thực sự là **số entry nhóm và overhead của Map** có vừa RAM hay không, chứ không nhất thiết tổng record của bucket.

Trong chương trình Java, một bucket với **100 record cùng khóa** vẫn được aggregate với ngân sách chỉ **một nhóm**, dù M mô phỏng chỉ 20 record.

### 5.3. Khi quá nhiều khóa phân biệt cùng một bucket

Nếu một phân vùng chứa quá nhiều **khóa phân biệt** để bảng nhóm vừa RAM, có thể:

- **Repartition** phân vùng đó bằng một hàm hash khác và ít nhất một lượt I/O nữa;
- Dùng **external sort/grouping** để nhóm các khóa bằng nhau cạnh nhau;
- Dùng một phương án **hybrid aggregation** tiền gom trong buffer và spill;
- Dùng cấu trúc tổng hợp có thể phân vùng theo range nếu phù hợp.

Chương trình Java cố tình **ném lỗi có thông điệp “recursive rehash or sort-based grouping”** khi số khóa phân biệt vượt ngân sách. Đây là hành vi **phát hiện spill**, không phải một bộ giải đệ quy hoàn chỉnh. Trong hệ thống sản xuất phải gắn thêm nhánh xử lý để tiếp tục đúng, không được biến lỗi đó thành kết luận không có dữ liệu hay bỏ bớt nhóm.

### 5.4. GROUP BY với SUM có thể gộp cục bộ

Nếu `SUM` là phép kết hợp có tính kết hợp (cẩn thận tràn số/kiểu dữ liệu), có thể cộng sơ bộ những record cùng khóa **ngay trong bộ nhớ trước khi flush**, giảm lượng dữ liệu ghi tạm. Nhưng `AVG` cần ghi tổng và số lượng, `COUNT(DISTINCT)` cần cấu trúc khác, `MEDIAN` không thể tự thay bằng cộng tổng. Không được tự giả sử mọi phép tổng hợp có thể gộp giống `SUM`.

Nếu key là chuỗi hoặc tuple, cần dùng cùng quy tắc equality/hash; còn khi dữ liệu có `NULL`, hãy nêu rõ ngữ nghĩa nhóm theo hệ quản trị đang dùng.

## 6. Ứng dụng 2: Grace hash join

Cho hai quan hệ R và S, cần phép nối:

```text
R JOIN S ON R.key = S.key.
```

Nếu phía build (thường quan hệ nhỏ hơn) quá lớn so với RAM, một phương án phổ biến là **Grace hash join**.

### 6.1. Pha 1: partition cả hai đầu vào

Dùng **chính xác cùng partition function**:

```text
p = h(key) mod F.
```

Quét R, ghi thành:

```text
R_0, R_1, ..., R_(F-1).
```

Quét S, ghi thành:

```text
S_0, S_1, ..., S_(F-1).
```

Với khóa bằng nhau:

```text
r.key=s.key
    => r thuộc R_i và s thuộc S_i
       cho cùng i.
```

Vì vậy chỉ cần nối từng cặp `(R_i,S_i)`; các cặp `(R_i,S_j)` với i≠j **không thể** chứa cặp khóa bằng nhau, nếu hash được dùng nhất quán.

### 6.2. Pha 2: build và probe từng cặp phân vùng

Với từng i:

1. Đọc phía build `R_i` và tạo hash table trong RAM.
2. Đọc từng record của `S_i`.
3. Tìm những record ở `R_i` cùng khóa và phát mọi cặp kết quả.
4. Giải phóng RAM của phân vùng i trước khi xử lý i+1.

Nếu quan hệ R_i có nhiều record cùng khóa, cần giữ **danh sách record/payload**, không chỉ đếm key, trừ khi bài toán chỉ yêu cầu **số cặp** nối.

### 6.3. Ví dụ có khóa lặp

Giả sử:

```text
R có key=1 xuất hiện 3 lần.
S có key=1 xuất hiện 3 lần.
```

Equi-join theo key sẽ tạo:

```text
3 * 3 = 9
```

cặp từ key=1, vì **mỗi record phía R ghép với mỗi record phía S có key bằng nhau**. Nếu các khóa khác đóng góp 4 cặp, tổng join cardinality là 13.

Trong mã mẫu, một bộ giải chỉ đếm số cặp:

```text
countR[key] = số record build có key ấy.
joinPairs += countR[s.key] mỗi khi đọc record s.
```

Cách này tính đúng **số cặp kết quả**, nhưng **không lưu mọi payload và không materialize kết quả join**. Muốn xuất cặp `(r,s)` thật, phải lưu record phía build và ghi output; có thể xuất cực nhiều cặp.

### 6.4. Chi phí I/O của Grace hash join một lượt

Đặt:

```text
N_R = số record của R.
N_S = số record của S.
B   = record/block.
```

Trong trường hợp phân vùng đủ cân bằng, buffer đủ, bỏ qua page cuối và overhead:

```text
Pha partition cả R và S:
  reads  ≈ (N_R+N_S)/B
  writes ≈ (N_R+N_S)/B.

Pha build/probe:
  reads  ≈ (N_R+N_S)/B.

Tổng (chưa ghi output):
  ≈ 3*(N_R+N_S)/B block I/Os.
```

Nếu kết quả join có `Z` record/pair và phải **ghi ra ngoài bộ nhớ**, cộng thêm khoảng:

```text
ceil(Z/B) output block writes,
```

chưa kể overhead/serialization. `Z` có thể lớn hơn rất nhiều `N_R+N_S`; chẳng hạn một khóa chung xuất hiện r lần trong R và s lần trong S thì riêng khóa ấy tạo `r*s` cặp.

**Quan trọng:** Không được dùng `3*(N_R+N_S)/B` như công thức chắc chắn của mọi hash join, vì có phân vùng chưa đầy block, skew cần repartition hoặc fallback, và chi phí ghi kết quả. Đây là phân tích cơ sở cho **một lượt phân hoạch hợp lệ**.

### 6.5. Nếu một phía build không vừa RAM?

Trước khi build `R_i`, kiểm tra ngân sách thực tế sau khi chừa buffer probe/output và metadata. Nếu `R_i` quá lớn, cần:

- Chia lại `(R_i,S_i)` bằng **cùng một hàm băm mới cho cả hai phía**;
- Đổi phía build nếu `S_i` nhỏ hơn và có thể vừa RAM;
- Dùng sort-merge join hoặc block nested-loop với chi phí được tính;
- Xử lý riêng khóa nặng để không lặp vô hạn.

Không được lặng lẽ giữ R_i trong `HashMap` vượt ngân sách rồi gọi đó là thuật toán out-of-core.

## 7. Repartition nhiều lượt và giới hạn của hash

Một lượt có thể chưa đủ nếu `N/F > M_work` hoặc do skew. Ta có thể đặt:

```text
depth=0: hash h0(key), tạo F partition.
depth=1: với bucket quá lớn, hash h1(key) mới.
depth=2: nếu vẫn lớn, dùng h2(key) mới.
...
```

**Không dùng y nguyên cùng hash và cùng bucket modulus ở mọi độ sâu**: một bucket có thể đi lại vào chính một bucket lớn như cũ, không đạt tiến triển. Dùng một hàm được salt khác ở mỗi tầng có thể thay đổi vị trí các **khóa khác nhau** và giúp chia nhỏ collision.

### 7.1. Ước lượng số mức phân hoạch

Trong mô hình lý tưởng các khóa được phân tán tốt vào F bucket mỗi lượt, sau d lượt kích thước trung bình của bucket khoảng:

```text
N / F^d.
```

Muốn trung bình khoảng không quá M_work:

```text
N / F^d <= M_work

=> d >= log_F(N/M_work).
```

Coi mỗi lượt đọc+ghi dữ liệu của bucket đang xét, số I/O có dạng trực giác:

```text
O((N/B) * (1 + log_F(N/M_work)))
```

trong điều kiện cân bằng đủ tốt và các phần dữ liệu thực sự trải qua số tầng tương ứng. Đây là **phân tích ước lượng có giả thiết**, không phải bảo đảm worst-case không điều kiện cho dữ liệu đối kháng hoặc nhiều khóa bằng nhau.

### 7.2. Phải có progress check

Một bộ giải đệ quy an toàn phải đo/ước lượng:

```text
largest child size,
number of distinct keys,
available memory for next phase.
```

Nếu bucket sau repartition vẫn **không giảm đáng kể**, cần đổi chiến lược. Các khả năng:

- Quá nhiều record có **cùng một khóa**;
- Tập khóa khác nhau nhưng hàm băm mới vẫn collision;
- Chọn số partition quá nhỏ;
- Hash phân bố kém trên dữ liệu thực tế;
- Bộ nhớ bị metadata/buffer chiếm nên ngân sách xử lý thực rất ít.

Đặt **giới hạn độ sâu** và fallback đã định nghĩa là biện pháp hữu ích để tránh vòng repartition vô tận.

### 7.3. Heavy key không thể chia nhỏ bằng hash(key) thuần túy

Nếu mọi record đều có `key=5`, thì với bất kỳ hàm hash chỉ phụ thuộc key:

```text
h(5) = cùng một bucket cho mọi record.
```

Thay salt vẫn giữ mọi record key=5 cùng bucket ở **mỗi tầng**, nên không thể chia 100.000 record đồng khóa thành nhiều partition **mà vẫn giữ quy tắc key-based thuần túy**. Có thể:

- GROUP BY: stream qua bucket và cộng một bộ đếm cho key=5;
- Hash join: xử lý key nặng đặc biệt, có thể chia payload thành chunk và join theo block/nested-loop hoặc sort-merge;
- Dùng một phương án phân phối dữ liệu theo khóa phụ/bucket thứ cấp nhưng **phải thiết kế lại cách khôi phục kết quả join**, tránh bỏ sót cross-products;
- Nếu mục tiêu thống kê, dùng các tổng hợp có thể kết hợp.

Bài học trọng tâm: **skew không chỉ là vấn đề chọn hash ngẫu nhiên hơn**. Việc cùng khóa phải gặp nhau tạo ra một giới hạn thật, nhất là với join có kết quả r×s.

## 8. Phân biệt record size, hash table size và metadata

Một hệ thống có:

```text
M=100000 "record slots"
```

không có nghĩa build table chứa đúng 100000 record thực tế. Hash table có:

- Hash bucket/array pointers;
- Key và payload;
- Load factor và khoảng trống;
- Object header, alignment, garbage collector nếu dùng JVM;
- Bộ đệm probe/output;
- Iterator, page descriptors;
- Các cấu trúc lập chỉ mục/tách khóa.

Nên tính theo byte:

```text
M_build_bytes =
    M_total_bytes - inputBuffers - outputBuffers
    - metadata - reserve.
```

Điều kiện vừa RAM phải là:

```text
estimatedBuildMemory(R_i) <= M_build_bytes.
```

Với GROUP BY, cần đo theo **số khóa phân biệt và kích thước mỗi aggregate entry**. Với join, thường theo **số record/payload build**, và có thể chọn phía build nhỏ hơn **trong từng partition**, nếu thuật toán hỗ trợ.

### 8.1. Điều chỉnh B và F theo byte

Trong file thật, B thường là **page size tính bằng bytes**; một record có thể chiếm nhiều byte. Nếu record không chia đều thành B record mỗi page, chỉ dùng `N/B` theo record để minh họa rồi khi triển khai phải chuyển sang:

```text
pages ≈ ceil(totalBytes / pageBytes).
```

Khi có nén, record có độ dài biến đổi hoặc format columnar, I/O vật lý còn phụ thuộc đóng gói page và compression.

## 9. Chọn hash và bảo đảm equality

Hàm hash partition phải:

1. **Xác định**: cùng key luôn có cùng partition cho cùng salt và F.
2. **Tương thích với equality**: nếu hai key được coi là bằng nhau trong phép group/join, chúng phải băm về cùng bucket. Ví dụ String so sánh không phân biệt hoa thường nhưng hash case-sensitive là không tương thích.
3. **Có phân phối hợp lý** trên dữ liệu thật.
4. **Nhất quán giữa các luồng/shard** của một lượt join.
5. **Có version/salt được lưu trong metadata** khi partition lưu trên disk để tái đọc/gộp/khôi phục đúng.

### 9.1. Mix và modulo

Mã Java demo dùng một bộ **mix 64-bit có salt** rồi tính:

```text
unsignedHash % F.
```

Nó xử lý cả khóa nguyên âm và tạo kết quả tái lập trong test. Đó là **hàm trộn xác định cho mô phỏng**, **không phải** chứng minh họ hash độc lập hoàn hảo, không phải hàm mật mã, và không có lời hứa chống khóa do đối thủ sinh ra sau khi biết salt.

Khi cần cận xác suất về kích thước bucket, phải nêu giả thiết **phân phối hash và sự phụ thuộc giữa các khóa**, rồi dùng bất đẳng thức/tail bound phù hợp. Một seed cố định là công cụ tái lập QA, không phải bằng chứng phân phối ngẫu nhiên lý tưởng.

### 9.2. NULL, collation và khóa ghép

Với join SQL, `NULL = NULL` thông thường không trả TRUE như phép equality giữa hai giá trị thường, trong khi GROUP BY có thể gom các NULL vào một nhóm. Đừng áp cùng một quy tắc hash/equality ngầm định cho cả hai nếu ngữ nghĩa bài toán khác. Với khóa ghép `(a,b)`, cách serialize và normalize phải thống nhất, có xét timezone, collation, Unicode normalization, dấu phân cách và giá trị NULL nếu cần.

## 10. Tính đúng của phép phân hoạch và của hai pha sau

### 10.1. Bất biến phát đúng một lần

Tại mỗi thời điểm quét đầu vào, mỗi record đã đọc thuộc đúng một trong hai trạng thái:

- Đang nằm trong **output buffer** tương ứng với bucket của khóa nó;
- Hoặc đã được **flush** vào đúng tệp/bucket đó.

Mỗi record được append một lần và một buffer khi flush được clear. Do đó sau khi đọc hết và flush các buffer cuối:

```text
Multiset(input)
  == multiset(P0) union ... union multiset(P(F-1)).
```

**Không mất record, không nhân đôi record**, miễn xử lý sự cố/ghi tệp đúng. Những record cùng key có cùng hash nên về cùng Pi.

### 10.2. Tính đúng của GROUP BY

Với một khóa x, do bất biến co-location, mọi record có key=x đều ở đúng một Pi. Cộng toàn bộ trọng số trong Pi bằng `SUM` với số học chính xác cho kết quả G(x), các partition còn lại không chứa key=x. Vì vậy hợp các bảng cục bộ là nhóm toàn cục đúng.

Khi có **hai khóa khác nhau nhưng cùng Pi**, vẫn phân biệt chúng bằng key trong `Map`. Phân hoạch không thay thế equality.

### 10.3. Tính đúng của equi-join

Với mọi cặp record `(r,s)` có `r.key=s.key`, điều kiện hash nhất quán bảo đảm chúng được đưa tới cùng cặp `(R_i,S_i)`. Pha join cục bộ duyệt mọi cặp matching trong cặp partition này nên không bỏ sót.

Ngược lại, mọi cặp được phát bởi join cục bộ phải được so key thật và thỏa điều kiện equality, nên không phát cặp sai. Mỗi record thuộc đúng một Pi, mỗi cặp matching chỉ có một i, nên không phát trùng cặp do partitioning. **Nếu dữ liệu gốc có các record trùng nhau theo giá trị nhưng là những dòng khác nhau, join vẫn có thể phát nhiều dòng giống nhau theo ngữ nghĩa bag** — đó là output hợp lệ, không phải lỗi partition trùng.

### 10.4. Phản ví dụ khác salt

Giả sử `R.key=42`, `S.key=42`. Nếu R dùng hash/salt A cho ra P0 còn S dùng hash/salt B cho ra P3, thuật toán chỉ join `(R_i,S_i)` sẽ **không hề so** hai record này và trả thiếu kết quả.

**Không thể chữa bằng cách so key thật trong từng bucket sau cùng**, vì cặp bằng nhau đã bị chia sang hai cặp partition khác nhau. Điều kiện cùng partition function là tiền đề correctness chứ không chỉ tối ưu hiệu năng.

## 11. Chi phí I/O: ghi công thức cho đúng

Cho tổng N record, F partition, kích thước thực tế của partition i là `N_i`, `SUM_i N_i=N`. Với mỗi input read theo block và output pages được flush đủ hoặc phần cuối:

```text
Q_read = ceil(N/B).

Q_write = SUM_{i=0..F-1} ceil(N_i/B).

Q_partition = Q_read + Q_write.
```

Với N lớn, F không quá lớn:

```text
Q_partition ≈ 2N/B + O(F).
```

Ở lượt xử lý các partition lần tiếp theo:

```text
Q_read_processing
    = SUM_i ceil(N_i/B)
```

nếu từng partition được đọc tuần tự một lần. Với GROUP BY cần cộng **chi phí ghi các nhóm output**; với join cần cộng **chi phí ghi Z cặp kết quả**, và với recursive spill cần cộng tất cả lượt đọc/ghi phát sinh.

### 11.1. Vì sao có `O(F)` cho page cuối?

Mỗi partition có tối đa một block cuối chưa đầy. Với F partition, nhiều nhất F block đầu ra có thể chịu phần lãng phí. Do đó không nên xem một output bucket với một record là “1/B lần write”; nếu thiết bị ghi theo page, vẫn phát sinh một page write.

Trong simulator, input N=20, B=4, output sizes `[4,4,2,10]`, nên:

```text
Reads  = 5.
Writes = 1+1+1+3 = 6.
```

Lượt group đọc lại từng bucket:

```text
GroupReads = 6.
```

Tổng mô phỏng partition+đọc nhóm:

```text
5+6+6 = 17 logical I/Os,
```

**chưa ghi output của GROUP BY**.

### 11.2. I/O của join có kết quả khổng lồ

Nếu R có 10.000 record key=x và S có 10.000 record key=x, riêng x có:

```text
Z_x = 10,000 * 10,000 = 100,000,000 output rows.
```

Không thuật toán join nào có thể **ghi vật lý đầy đủ** 100 triệu dòng output với ít hơn số block đủ chứa chúng. Vì vậy đánh giá chỉ số I/O đầu vào mà bỏ **output size** có thể rất sai.

Nếu chỉ yêu cầu **COUNT(*) của join**, có thể dùng các bộ đếm nhóm và tính tích, tránh materialize toàn bộ 100 triệu cặp. Đó là **bài toán đầu ra khác** với trả toàn bộ rows.

### 11.3. Trường hợp chỉ cần một lần scan

Nếu toàn bộ số nhóm hoặc phía build thực ra đã vừa RAM, có thể xử lý bằng một lượt quét trực tiếp mà **không ghi tạm các phân vùng**, tiết kiệm I/O. External partitioning là kỹ thuật để **thỏa ngân sách bộ nhớ**, không nên áp cứng khi không cần.

### 11.4. Độ phức tạp CPU

Một lượt partition còn tốn:

```text
O(N) lần tính hash và append buffer
```

trong mô hình xử lý mỗi record O(1). Grouping có chi phí kỳ vọng theo hash table, join có chi phí xây/probe bảng, còn việc sort fallback có thể tốn nhiều so sánh CPU. **I/O complexity** và **CPU complexity** phải trình bày riêng; một thuật toán giảm I/O có thể dùng thêm CPU để nén hoặc chọn hash.

## 12. Chiến lược xử lý skew và phân vùng quá lớn

| Tình huống | Tác động | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Các khóa phân tán đều, mỗi bucket vừa | Một lượt partition là đủ | Chia rồi group/join từng bucket |
| Một số bucket lớn do nhiều khóa khác nhau | Bảng cục bộ không vừa RAM | Rehash bucket bằng salt mới, nhiều lượt |
| Một khóa cực nhiều record, GROUP BY SUM | Bucket record lớn, số nhóm nhỏ | Stream và gộp bộ đếm theo khóa |
| Một khóa cực nhiều record, hash join | Build records lớn, output có thể r×s | Skew-aware join, block nested-loop, sort-merge/chunk |
| F quá lớn khiến nhiều page cuối chưa đầy | Nhiều write và overhead metadata | Giảm F, gom buffer, phân hoạch nhiều tầng |
| Hash/equality không tương thích | Sai kết quả join/group | Chuẩn hóa key và dùng cùng partition function |
| M quá nhỏ cho F input/output buffers | Không thể mở đủ frame cùng lúc | Giảm F hoặc chọn thuật toán khác |
| Buckets tiếp tục không nhỏ khi repartition | Vòng lặp và I/O không có tiến triển | Detect progress, switch fallback |

### 12.1. Repartition không phải công thức chữa mọi dữ liệu

Một cách làm không an toàn:

```text
if bucket.size > M:
    repartition(bucket, new hash)
    recursively repeat forever
```

Nếu bucket gồm toàn record cùng key, kích thước **không giảm** sau mỗi lần. Thiết kế đúng cần giới hạn độ sâu hoặc phát hiện `maxChildSize >= parentSize` qua nhiều lượt, rồi xử lý riêng theo kiểu toán tử. Với group SUM có thể chỉ cần một bộ đếm; với equi-join nặng cần tính output/probe theo từng chunk.

### 12.2. Chọn phía build theo từng partition

Ở một cặp `(R_i,S_i)`, nếu R_i lớn nhưng S_i nhỏ hơn và vừa RAM, có thể **đổi phía build** để dùng ít bộ nhớ hơn. Điều này không tự thay đổi kết quả equality join nếu phép phát output được thực hiện đúng. Với outer join, null-preservation và thứ tự semantics phải được xem xét riêng, không đổi tùy tiện như inner join.

### 12.3. Trường hợp dữ liệu cập nhật liên tục

Hash partition file tĩnh dùng tốt cho batch. Với luồng liên tục, hệ thống có thể phải quản lý writer buffers, checkpoint, thời điểm đóng partition, watermark/window và crash recovery. Nếu phải cập nhật file partition đang mở, có thể phát sinh random writes; nên lập kế hoạch append/log hoặc compaction phù hợp. Những yêu cầu này nằm ngoài mô hình một lượt partition có đầu vào hữu hạn.

## 13. Chương trình Java 17+ minh họa

**Tệp: `ExternalHashPartitionDemo.java`.**

Để kiểm thử **không tạo file ngoài workspace**, chương trình dùng `VirtualDisk` với dữ liệu lưu trong mảng/list Java, nhưng ép mỗi lần đọc đầu vào qua hàm `readBlock`, giữ **một input page và F output pages** trong thuật toán partition, và tăng bộ đếm I/O khi một page được đọc/ghi. Những list `diskBuckets` đứng thay cho **tệp phân vùng ngoài đĩa** chỉ trong simulator; toàn bộ list vẫn nằm trong heap JVM để có thể đối chiếu kết quả.

**Không được** mô tả demo là đã xử lý một tệp terabyte bằng RAM cố định: đây là **mô phỏng chi phí I/O và bất biến dữ liệu**, không phải storage engine thực. Để dùng thật, thay `VirtualDisk` và các bucket lists bằng `FileChannel`/file page buffer, xử lý lỗi I/O, open-file limits, partial block và durability.

Chương trình có:

1. **Partitioner có buffer**: `partition()` từ một `VirtualDisk`, từ chối `(F+1)*B > M`, ghi mỗi bucket thành các block đủ B record hoặc block cuối chưa đầy.
2. **GROUP BY exact**: `groupPartitions()` đọc lại từng partition, dùng `HashMap` tạm theo khóa rồi nối các kết quả bằng `TreeMap`; nếu số khóa phân biệt trong một partition vượt ngân sách cấu hình thì báo cần **recursive rehash hoặc sort-based grouping**, không âm thầm dùng quá RAM.
3. **Grace hash join cardinality**: `joinCardinality()` yêu cầu hai input partition cùng F, B, salt; từ chối nếu build bucket vượt ngân sách, đếm chính xác số cặp matching mà không tạo mọi dòng output.
4. **Oracle độc lập**: `exactGroups()` tính group sums trực tiếp trên dữ liệu nhỏ; `exactJoinCount()` dùng nested loops kiểm tra từng cặp R×S.
5. **QA**: 300 luồng random GROUP BY, kiểm tra phân hoạch và I/O; 400 bài join random so với oracle; thử skew 100 bản ghi cùng key và phát hiện join build spill; thử khác salt bị từ chối.

### 13.1. Mã Java đầy đủ

```java
import java.util.*;

public class ExternalHashPartitionDemo {
    record Row(int key, long weight) {}

    static final class VirtualDisk {
        final List<Row> rows;
        final int blockSize;
        long blockReads;

        VirtualDisk(List<Row> rows, int blockSize) {
            if (blockSize <= 0) throw new IllegalArgumentException("B <= 0");
            this.rows = List.copyOf(Objects.requireNonNull(rows));
            this.blockSize = blockSize;
        }

        int blockCount() {
            return (int) ((rows.size() + (long) blockSize - 1) / blockSize);
        }

        List<Row> readBlock(int index) {
            if (index < 0 || index >= blockCount())
                throw new IndexOutOfBoundsException("invalid block");
            blockReads++;
            int from = index * blockSize;
            return rows.subList(
                    from, Math.min(from + blockSize, rows.size()));
        }
    }

    record Partitioned(
            int fanOut, int blockSize, long salt,
            List<List<Row>> buckets, long reads, long writes,
            int maxBufferRecords) {
        int size() {
            int sum = 0;
            for (List<Row> bucket : buckets) sum += bucket.size();
            return sum;
        }

        int largestBucket() {
            int best = 0;
            for (List<Row> bucket : buckets)
                best = Math.max(best, bucket.size());
            return best;
        }
    }

    // A deterministic mixer is used for repeatable tests.
    // It is not a proof of fully independent random hashing.
    static int bucket(int key, long salt, int fanOut) {
        if (fanOut <= 0) throw new IllegalArgumentException("fanOut <= 0");
        long x = ((long) key ^ salt) + 0x9E3779B97F4A7C15L;
        x = (x ^ (x >>> 30)) * 0xBF58476D1CE4E5B9L;
        x = (x ^ (x >>> 27)) * 0x94D049BB133111EBL;
        x ^= x >>> 31;
        return (int) Long.remainderUnsigned(x, fanOut);
    }

    // One input block plus fanOut output blocks of B records.
    // The bucket lists stand in for external files: they are
    // stored in Java heap ONLY to make the simulator testable.
    static Partitioned partition(
            VirtualDisk source, int memoryRecords,
            int fanOut, long salt) {
        Objects.requireNonNull(source);
        int b = source.blockSize;
        if (fanOut < 1
                || (long) (fanOut + 1) * b > memoryRecords) {
            throw new IllegalArgumentException(
                    "Need (fanOut+1)*B <= M");
        }

        List<List<Row>> diskBuckets = new ArrayList<>();
        for (int p = 0; p < fanOut; p++) {
            diskBuckets.add(new ArrayList<>());
        }
        Row[][] outputBuffers = new Row[fanOut][b];
        int[] used = new int[fanOut];
        long writes = 0;

        for (int inputBlock = 0;
                inputBlock < source.blockCount(); inputBlock++) {
            for (Row row : source.readBlock(inputBlock)) {
                Objects.requireNonNull(row);
                if (row.weight() < 0)
                    throw new IllegalArgumentException(
                            "Negative weight not supported in demo");
                int p = bucket(row.key(), salt, fanOut);
                outputBuffers[p][used[p]++] = row;
                if (used[p] == b) {
                    for (int j = 0; j < b; j++)
                        diskBuckets.get(p).add(outputBuffers[p][j]);
                    Arrays.fill(outputBuffers[p], null);
                    used[p] = 0;
                    writes++;
                }
            }
        }
        for (int p = 0; p < fanOut; p++) {
            if (used[p] > 0) {
                for (int j = 0; j < used[p]; j++)
                    diskBuckets.get(p).add(outputBuffers[p][j]);
                Arrays.fill(outputBuffers[p], null);
                used[p] = 0;
                writes++; // partial final page still costs one I/O
            }
        }
        List<List<Row>> result = new ArrayList<>();
        for (List<Row> each : diskBuckets) {
            result.add(List.copyOf(each));
        }
        return new Partitioned(
                fanOut, b, salt, List.copyOf(result),
                source.blockReads, writes, (fanOut + 1) * b);
    }

    static int blocks(int n, int b) {
        return (n + b - 1) / b;
    }

    static long expectedPartitionWrites(Partitioned p) {
        long sum = 0;
        for (List<Row> each : p.buckets()) {
            sum += blocks(each.size(), p.blockSize());
        }
        return sum;
    }

    static Map<Integer, Long> exactGroups(List<Row> rows) {
        Map<Integer, Long> result = new TreeMap<>();
        for (Row row : rows) {
            result.merge(row.key(), row.weight(), Math::addExact);
        }
        return result;
    }

    record GroupResult(Map<Integer, Long> groups,
                       long readBlocks, int largestDistinctKeys) {}

    // Read each partition sequentially and aggregate in RAM.
    // If a partition has too many DISTINCT keys, fail explicitly
    // rather than pretending the hash table fits M.
    static GroupResult groupPartitions(
            Partitioned p, int maxDistinctKeysInMemory) {
        if (maxDistinctKeysInMemory < 1)
            throw new IllegalArgumentException("max groups < 1");
        Map<Integer, Long> global = new TreeMap<>();
        long reads = 0;
        int largestDistinct = 0;

        for (List<Row> diskBucket : p.buckets()) {
            Map<Integer, Long> local = new HashMap<>();
            for (int begin = 0; begin < diskBucket.size();
                    begin += p.blockSize()) {
                reads++; // one page read
                int end = Math.min(
                        begin + p.blockSize(), diskBucket.size());
                for (int j = begin; j < end; j++) {
                    Row row = diskBucket.get(j);
                    if (!local.containsKey(row.key())
                            && local.size() == maxDistinctKeysInMemory) {
                        throw new IllegalStateException(
                                "Partition needs recursive rehash or "
                                + "sort-based grouping");
                    }
                    local.merge(row.key(), row.weight(), Math::addExact);
                }
            }
            largestDistinct = Math.max(largestDistinct, local.size());
            for (Map.Entry<Integer, Long> e : local.entrySet()) {
                if (global.put(e.getKey(), e.getValue()) != null)
                    throw new AssertionError(
                            "Equal keys were split across partitions");
            }
        }
        return new GroupResult(
                Collections.unmodifiableMap(global),
                reads, largestDistinct);
    }

    record JoinResult(long matchingPairs, long readBlocks) {}

    // Count join rows, WITHOUT materializing them.
    // Each build-side bucket must fit the explicit row budget.
    static JoinResult joinCardinality(
            Partitioned left, Partitioned right,
            int maxBuildRowsInMemory) {
        if (maxBuildRowsInMemory <= 0)
            throw new IllegalArgumentException("bad build memory");
        if (left.fanOut() != right.fanOut()
                || left.blockSize() != right.blockSize()
                || left.salt() != right.salt()) {
            throw new IllegalArgumentException(
                    "Join requires identical partition functions");
        }
        long pairs = 0, reads = 0;
        for (int p = 0; p < left.fanOut(); p++) {
            List<Row> build = left.buckets().get(p);
            List<Row> probe = right.buckets().get(p);
            if (build.size() > maxBuildRowsInMemory) {
                throw new IllegalStateException(
                        "Build bucket exceeds RAM; repartition or "
                        + "use sort-merge / skew-aware join");
            }
            reads += blocks(build.size(), left.blockSize());
            reads += blocks(probe.size(), left.blockSize());

            Map<Integer, Long> count = new HashMap<>();
            for (Row row : build)
                count.merge(row.key(), 1L, Math::addExact);
            for (Row row : probe) {
                pairs = Math.addExact(
                        pairs, count.getOrDefault(row.key(), 0L));
            }
        }
        return new JoinResult(pairs, reads);
    }

    static long exactJoinCount(List<Row> left, List<Row> right) {
        long matches = 0;
        for (Row a : left) {
            for (Row b : right) {
                if (a.key() == b.key()) matches++;
            }
        }
        return matches;
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void example() {
        final int B = 4, M = 20, F = 4;
        final long SALT = 20261110L;
        List<Row> rows = List.of(
                new Row(7, 2), new Row(2, 5),
                new Row(-3, 1), new Row(7, 3),
                new Row(18, 4), new Row(2, 1),
                new Row(42, 2), new Row(-3, 8),
                new Row(7, 4), new Row(18, 2),
                new Row(2, 6), new Row(42, 1),
                new Row(5, 9), new Row(5, 1),
                new Row(18, 1), new Row(42, 2),
                new Row(7, 1), new Row(2, 2),
                new Row(5, 2), new Row(18, 3)
        );
        Partitioned p = partition(
                new VirtualDisk(rows, B), M, F, SALT);
        GroupResult grouped = groupPartitions(p, 6);
        check(p.size() == rows.size()
                && grouped.groups().equals(exactGroups(rows)),
                "Group-by lost or duplicated input records");
        check(p.reads() == blocks(rows.size(), B)
                && p.writes() == expectedPartitionWrites(p)
                && grouped.readBlocks() == p.writes(),
                "Wrong partition/read transfer count");
        System.out.println(
                "Config: N=" + rows.size() + ", M=" + M
                + ", B=" + B + ", fanOut=" + F
                + ", bufferRecords=" + p.maxBufferRecords());
        System.out.println(
                "Partition sizes: "
                + p.buckets().stream().map(List::size).toList());
        System.out.println(
                "Partition I/O: reads=" + p.reads()
                + ", writes=" + p.writes()
                + ", groupReads=" + grouped.readBlocks());
        System.out.println("Exact grouped sums: "
                + grouped.groups());

        List<Row> r = List.of(
                new Row(1, 10), new Row(2, 11),
                new Row(1, 20), new Row(3, 12),
                new Row(4, 13), new Row(5, 14),
                new Row(1, 15), new Row(6, 16),
                new Row(8, 17)
        );
        List<Row> s = List.of(
                new Row(1, 99), new Row(1, 98),
                new Row(2, 55), new Row(4, 56),
                new Row(7, 22), new Row(5, 77),
                new Row(1, 100), new Row(6, 101)
        );
        Partitioned pr = partition(
                new VirtualDisk(r, B), M, F, SALT);
        Partitioned ps = partition(
                new VirtualDisk(s, B), M, F, SALT);
        JoinResult join = joinCardinality(pr, ps, M - B);
        check(join.matchingPairs() == exactJoinCount(r, s)
                && join.matchingPairs() == 13L,
                "Grace hash join missed equal-key rows");
        System.out.println("Equality join: pairs="
                + join.matchingPairs() + ", buildMaxBucket="
                + pr.largestBucket() + ", probeReads="
                + join.readBlocks());

        List<Row> skew = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
            skew.add(new Row(5, 1));
        }
        Partitioned skewP = partition(
                new VirtualDisk(skew, B), M, F, SALT);
        GroupResult skewGroup = groupPartitions(skewP, 1);
        check(skewP.largestBucket() == 100
                && skewGroup.groups().get(5) == 100L,
                "Single heavy key should aggregate with one group");
        boolean joinSpill = false;
        try {
            joinCardinality(skewP, ps, M - B);
        } catch (IllegalStateException expected) {
            joinSpill = true;
        }
        check(joinSpill, "Skewed build side must be detected");
        System.out.println("Heavy key: maxBucket="
                + skewP.largestBucket() + ", distinctGroups="
                + skewGroup.largestDistinctKeys()
                + ", joinBuildSpillDetected=" + joinSpill);

        boolean incompatible = false;
        try {
            Partitioned different = partition(
                    new VirtualDisk(s, B), M, F, SALT + 1);
            joinCardinality(pr, different, M - B);
        } catch (IllegalArgumentException expected) {
            incompatible = true;
        }
        check(incompatible, "Hash mismatch must fail");
        System.out.println(
                "Different hash salts rejected: " + incompatible);
    }

    static void randomOracleTests() {
        SplittableRandom rng = new SplittableRandom(5172026L);
        final int B = 4, M = 20, F = 4;
        long groupUpdates = 0, groupQueries = 0;
        for (int trial = 0; trial < 300; trial++) {
            int n = rng.nextInt(1, 201);
            List<Row> data = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                data.add(new Row(rng.nextInt(-20, 21),
                        rng.nextLong(0, 11)));
            }
            Partitioned p = partition(
                    new VirtualDisk(data, B), M, F, 9000L + trial);
            GroupResult result = groupPartitions(p, 50);
            Map<Integer, Long> expected = exactGroups(data);
            check(result.groups().equals(expected)
                    && p.size() == n
                    && p.reads() == blocks(n, B)
                    && p.writes() == expectedPartitionWrites(p)
                    && result.readBlocks() == p.writes(),
                    "Random partitioned group-by mismatch");
            groupUpdates += n;
            groupQueries += expected.size();
        }
        int joinCases = 0;
        for (int trial = 0; trial < 400; trial++) {
            List<Row> left = new ArrayList<>(), right = new ArrayList<>();
            int nr = rng.nextInt(1, 13), ns = rng.nextInt(1, 17);
            for (int i = 0; i < nr; i++) {
                left.add(new Row(rng.nextInt(-6, 7), 1));
            }
            for (int i = 0; i < ns; i++) {
                right.add(new Row(rng.nextInt(-6, 7), 1));
            }
            long salt = 40_000L + trial;
            Partitioned pr = partition(
                    new VirtualDisk(left, B), M, F, salt);
            Partitioned ps = partition(
                    new VirtualDisk(right, B), M, F, salt);
            JoinResult got = joinCardinality(pr, ps, M - B);
            check(got.matchingPairs() == exactJoinCount(left, right),
                    "Random grace-hash join count mismatch");
            joinCases++;
        }
        System.out.println("Random oracle QA: PASS (300 group streams, "
                + groupUpdates + " records, "
                + groupQueries + " group keys, "
                + joinCases + " joins)");
    }

    public static void main(String[] args) {
        example();
        randomOracleTests();
    }
}
```

### 13.2. Biên dịch và chạy

Lưu mã vào `ExternalHashPartitionDemo.java` rồi dùng JDK 17 trở lên:

```bash
javac ExternalHashPartitionDemo.java
java ExternalHashPartitionDemo
```

**Stdout chính xác với seed trong chương trình:**

```text
Config: N=20, M=20, B=4, fanOut=4, bufferRecords=20
Partition sizes: [4, 4, 2, 10]
Partition I/O: reads=5, writes=6, groupReads=6
Exact grouped sums: {-3=9, 2=14, 5=12, 7=10, 18=10, 42=5}
Equality join: pairs=13, buildMaxBucket=6, probeReads=8
Heavy key: maxBucket=100, distinctGroups=1, joinBuildSpillDetected=true
Different hash salts rejected: true
Random oracle QA: PASS (300 group streams, 28815 records, 9652 group keys, 400 joins)
```

### 13.3. Đọc kết quả đúng ngữ nghĩa

**Config:** `N=20`, `M=20`, `B=4`, `F=4`. Đây là bộ mẫu nhỏ dễ theo dõi page. Bố trí một input buffer và bốn output buffers cần đúng 20 record slots trong mô hình. Phần kiểm thử phía dưới có nhiều luồng với `N` lên tới **200**, lớn hơn `M=20`, và trường hợp key nặng có 100 record. Không suy N=20 ở ví dụ đầu là điều kiện thiết kế cho toàn thuật toán.

**Partition sizes:** `[4,4,2,10]` được tạo bởi bộ mix có salt cố định trên 20 record. **Các giá trị này không được suy từ `key % 4` đơn giản**, vì mã dùng hash mix; ví dụ modulo ba bucket ở mục 2 chỉ là minh họa tính tay.

**Partition I/O:** Input có 20/4 = 5 page; các bucket viết lần lượt 1,1,1,3 page nên tổng 6 writes. Khi aggregate từng partition, bộ mô phỏng đọc lại đúng 6 page. Tổng riêng hai pha là 17 logical transfers, **chưa ghi kết quả group**.

**Exact grouped sums:** Bảng kết quả bao gồm cả khóa âm −3. Mỗi khóa chỉ xuất hiện một lần trong bảng groups, và tổng trọng số trùng với oracle quét toàn bộ bản ghi.

**Equality join:** Có 13 cặp matching. Code kiểm tra với nested-loop oracle. `buildMaxBucket=6` nhỏ hơn ngân sách `M−B=16` record trong ví dụ; `probeReads=8` là tổng lượt đọc lại các partition của **hai** đầu vào theo cách đếm page trong demo, không phải số record kết quả.

**Heavy key:** 100 record cùng key về một bucket lớn hơn M. GROUP BY vẫn dùng một nhóm và tính được tổng 100. Nhưng nếu muốn build bảng join chứa các record/payload, `100 > M−B`, chương trình phát hiện **spill**. Mã **không tự triển khai thuật toán fallback**, do đó không hề giả vờ materialize được phép join này.

**Different hash salts:** Bộ giải join từ chối hai phía dùng salt khác nhau, giúp tránh sai tính đúng do cùng key bị đưa vào hai partition không tương ứng.

**Random oracle QA:** 300 luồng group-by với tổng **28.815 record**, đối chiếu **9.652 khóa nhóm**; 400 bài join ngẫu nhiên có khóa dương/âm đối chiếu nested loop. Mỗi lần kiểm tra còn xác nhận tổng kích thước các partition, số input page read và số output page write tính theo từng bucket.

## 14. Pseudocode cho hệ thống ngoài bộ nhớ thật

Mã trên là simulator, vì vậy một triển khai thực sự nên phân tách hai tầng:

```text
EXTERNAL_PARTITION(inputFile, partitionFiles, B, F):
    allocate 1 B-byte input page
    allocate F B-byte output pages

    while read(inputFile, inputPage):
        for each decoded record in inputPage:
            p = partitionHash(key, schemaSalt, F)
            serialize record to outputPage[p]
            if outputPage[p] full:
                append exactly one page to partitionFile[p]
                reset outputPage[p]

    for each p:
        if outputPage[p] nonempty:
            write final partial page with length metadata
            reset outputPage[p]
    close / flush according to durability contract
```

Nếu record dài biến đổi, output page phải có **length/offset directory**, checksum hoặc metadata thích hợp. Các page chưa đầy cần phân biệt **valid record count** và padding để không phát những record giả khi đọc lại.

### 14.1. Pipeline an toàn cho group-by

```text
for each bucket:
    attempt in-memory hash aggregation with explicit memory budget

    if aggregation fits:
        emit each (key,sum) once
    else:
        spill bucket and recursively repartition
        OR switch to external sort-based grouping
```

Khi dữ liệu có một khóa nặng, cần tận dụng tính chất tổng hợp: đếm một khóa có thể stream được, thay vì ép mọi bucket phải có ít record hơn M.

### 14.2. Pipeline an toàn cho join

```text
partition R and S with SAME hash function
for each corresponding pair (R_i,S_i):
    choose smaller feasible build side
    if build side fits working memory:
        build hash table, probe other side
        emit matching rows through buffered output
    else:
        recursively repartition BOTH sides with SAME NEW hash
        OR process skew/choose sort-merge/block nested-loop
```

Nếu R_i và S_i được phân hoạch lại nhưng dùng **salt khác nhau**, tính đúng hỏng. Nếu cùng salt mới nhưng có một key quá nặng, cần fallback, không được repartition vô hạn.

### 14.3. Quản lý file, crash và checkpoint

Đối với dữ liệu sản xuất:

- Ghi rõ số partition, salt/version, schema, record format, valid length của page cuối.
- Xác nhận tất cả buffered output đã flush trước khi đọc bucket để xử lý.
- Nếu tiến trình crash giữa partition, không coi các file tạm đã đầy đủ; cần commit marker/manifest hoặc làm lại an toàn.
- Dọn file tạm **sau khi** kết quả được commit, tránh xóa đầu vào trước khi output hợp lệ.
- Giới hạn số file handle đang mở; nhiều partition logic có thể cần writer pool.
- Kiểm tra free disk space, I/O error và checksum nếu yêu cầu.
- Phân biệt flush vào OS cache với `fsync`/durability.
- Nếu cần thứ tự global, hash partition **không tạo ra thứ tự sắp xếp**.

## 15. Phân biệt hash partition, range partition và sort

| Kỹ thuật | Cách chia | Phù hợp | Giới hạn |
| --- | --- | --- | --- |
| **Hash partition** | `hash(key) -> bucket` | Group-by, equi-join, chia workload theo key | Không giữ thứ tự key; skew/collision |
| **Range partition** | Chia theo khoảng giá trị khóa | Range query, sort/merge, xử lý theo thứ tự | Chọn ranh giới khó khi dữ liệu lệch |
| **External merge sort** | Tạo run sorted rồi merge nhiều ngả | ORDER BY, GROUP BY bằng sort, sort-merge join | Tốn nhiều pass đọc/ghi nếu N≫M |
| **Hybrid hash aggregation** | Gom sơ bộ trong RAM rồi spill | Giảm ghi tạm khi nhiều record chung khóa | Quản lý flush và merge partial state |
| **Block nested-loop join** | Quét một phía theo chunk, quét phía kia | Fallback khi hash build không vừa | Có thể tốn nhiều lần quét và I/O |
| **Skew-aware hash join** | Tách xử lý khóa nặng/các key phổ biến | Data skew mạnh, output lớn | Phải giữ đúng bag semantics |

**Không có một lựa chọn luôn tốt nhất.** Nếu query cần thứ tự, sort có thể phù hợp hơn. Nếu chỉ equality/group theo key và phân bố cân bằng, hash partition rất hiệu quả. Nếu key nặng, phải có chiến lược riêng.

## 16. Lỗi thường gặp

1. Giữ toàn bộ N record trong `HashMap` rồi gọi đó là thuật toán ngoài bộ nhớ.
2. Coi mọi record đọc từ disk là một block I/O riêng, bỏ khả năng quét B record/page.
3. Không định nghĩa rõ N,M,B và đơn vị record/byte.
4. Tạo F output buffers nhưng quên input buffer, dẫn đến `(F+1)B>M`.
5. Chọn F bằng M/B thay vì chừa ít nhất một input frame.
6. Không chừa RAM cho metadata, hash table, page descriptors và runtime.
7. Ghi mỗi record thành một I/O nhỏ dù có thể dùng output buffer.
8. Không flush các output buffers còn dữ liệu vào cuối lượt.
9. Xử lý padding của page cuối như record hợp lệ.
10. Tính số block write bằng `floor(N/B)` thay vì tổng `ceil(N_i/B)`.
11. Bỏ overhead O(F) của những page cuối chưa đầy.
12. Giả định output partition sizes luôn bằng đúng N/F.
13. Coi bucket trung bình vừa RAM nghĩa tất cả bucket chắc chắn vừa RAM.
14. Không phát hiện bucket quá lớn trước khi dựng bảng hash.
15. Dùng hash khác nhau cho R và S trong equi-join.
16. Coi hai key có cùng bucket là cùng khóa.
17. Dùng `%F` trực tiếp cho key âm rồi nhận bucket index âm.
18. Dùng hash không tương thích với equality/normalization/collation.
19. Chia một key qua nhiều partition mà không thiết kế lại phép nối/gom.
20. Tưởng tăng F sẽ chia nhỏ một khóa có hàng triệu record.
21. Rehash bằng đúng salt và modulus cũ khi bucket vẫn quá lớn.
22. Repartition vô hạn một bucket toàn cùng key.
23. Bỏ qua progressive check/giới hạn độ sâu.
24. Nói hash tốt sẽ loại hoàn toàn skew do dữ liệu có khóa nặng.
25. Nhầm số record bucket với số khóa phân biệt cần cho GROUP BY.
26. Buộc GROUP BY một key nặng phải fit toàn bộ record vào RAM.
27. Coi số khóa ít là đủ cho hash join chứa mọi payload của build side.
28. Chỉ giữ một record mỗi key khi join cần bag semantics.
29. Quên cặp key có r record bên R và s record bên S tạo r*s cặp.
30. Bỏ chi phí ghi kết quả Z của join khỏi tính tổng I/O.
31. Coi hash partition tự sắp xếp record theo key.
32. Dùng count of join pairs mà gọi là đã materialize kết quả join.
33. Gộp các kết quả GROUP BY theo bucket index thay vì key thật.
34. Nếu partial aggregate được spill, quên gộp các partial sum cùng key khi khôi phục.
35. Tính SUM bằng int và để overflow mà không phát hiện.
36. Giữ một `TreeMap` toàn bộ kết quả trong RAM trong production dù kết quả quá lớn; cần stream output.
37. Dùng random seed cố định trong test làm bảo đảm phân phối bucket cho mọi input.
38. Coi một hash mixer không mật mã là chống được đối thủ chọn khóa.
39. Không lưu version/seed/hash khi checkpoint partition files.
40. Đọc bucket trước khi writer flush hết output cuối.
41. Mở hàng chục nghìn file handle cùng lúc vượt giới hạn OS.
42. Bỏ qua I/O tệp tạm và write amplification qua nhiều tầng.
43. Tuyên bố `3(N_R+N_S)/B` là chi phí join chính xác trong mọi trường hợp.
44. Đánh đồng kết quả simulator chạy trên heap với external I/O vật lý của SSD.
45. Không phân biệt INNER JOIN, OUTER JOIN và ngữ nghĩa NULL khi đổi phía build.
46. Dựa vào benchmark duy nhất mà không thử skew, key trùng và key âm.
47. Không test rằng các record bằng khóa luôn rơi cùng bucket qua mọi input.
48. Không đối chiếu group sums với oracle Map và join cardinality với nested-loop trên dữ liệu nhỏ.
49. Khi crash, dùng bucket files chưa commit như thể đã đầy đủ.
50. Xóa file tạm trước khi output được xác nhận thành công.

## 17. Bài tập có đáp án

**Bài 1.** Trong mô hình ngoài RAM, N,M,B biểu thị gì?

**Đáp án:** N record đầu vào; M record RAM làm việc; B record mỗi block truyền I/O.

**Bài 2.** Nếu B=100 record, N=1050 record, phải đọc bao nhiêu block khi quét?

**Đáp án:** `ceil(1050/100)=11` block.

**Bài 3.** Vì sao hash partition hữu ích khi N>M?

**Đáp án:** Nó chia bản ghi theo key thành nhiều phân vùng trên đĩa để xử lý từng tập con bằng RAM có giới hạn.

**Bài 4.** Với cùng key, hai record có được sang hai partition khác nhau không?

**Đáp án:** Không nếu thuật toán partition theo key nhất quán; cùng key phải co-locate.

**Bài 5.** Hai key khác nhau có thể cùng partition không?

**Đáp án:** Có, do hash collision; xử lý trong partition vẫn phải so key thật.

**Bài 6.** M=20, B=4, tối đa bao nhiêu output buffers nếu chừa một input buffer?

**Đáp án:** `floor(20/4)-1=4`.

**Bài 7.** Với F=4, B=4, bộ đệm input+output chiếm bao nhiêu record slots?

**Đáp án:** `(4+1)*4=20`.

**Bài 8.** N=20, B=4, quét một lượt tốn bao nhiêu input block reads?

**Đáp án:** 5.

**Bài 9.** Bốn partition có sizes `[4,4,2,10]`, B=4, writes bao nhiêu?

**Đáp án:** `1+1+1+3=6` block writes.

**Bài 10.** Nếu aggregate đọc lại đúng bốn partition ở bài 9, tốn bao nhiêu block reads?

**Đáp án:** 6.

**Bài 11.** Tổng partition+đọc nhóm trong ví dụ bài 8–10?

**Đáp án:** `5+6+6=17` logical I/O, chưa ghi output.

**Bài 12.** F=3, `partition(key)=floorMod(key,3)`, khóa −1 vào bucket nào?

**Đáp án:** Bucket 2.

**Bài 13.** Hash partition có sắp xếp bản ghi theo key không?

**Đáp án:** Không; nó chỉ đưa cùng key về cùng bucket.

**Bài 14.** Trong GROUP BY SUM, một bucket chứa 100.000 record cùng một key có bắt buộc giữ toàn bộ record RAM không?

**Đáp án:** Không; có thể stream và giữ một tổng cho key ấy.

**Bài 15.** Nếu bucket có quá nhiều khóa phân biệt để Map cục bộ vừa RAM, xử lý thế nào?

**Đáp án:** Repartition bằng hash mới có progress check hoặc chuyển sang sort-based grouping/hybrid spill.

**Bài 16.** Vì sao không thể cho một khóa duy nhất vào nhiều bucket bằng hash(key) đơn thuần?

**Đáp án:** Mọi record của cùng key có cùng giá trị hash, nên cùng một bucket ở mỗi lượt.

**Bài 17.** Hai quan hệ R,S trong Grace hash join phải dùng gì giống nhau?

**Đáp án:** Cùng partition function, gồm cách normalize key, hash, salt/seed và F.

**Bài 18.** Nếu R.key=1 có ba record, S.key=1 có hai record, join có bao nhiêu cặp từ key=1?

**Đáp án:** `3*2=6` cặp.

**Bài 19.** Nếu key=1 có ba record mỗi phía, join tạo bao nhiêu cặp?

**Đáp án:** 9.

**Bài 20.** Nếu muốn trả mọi cặp join, `COUNT(*)` có thay thế materialization không?

**Đáp án:** Không. COUNT chỉ trả số cặp, còn materialization phải ghi/stream từng cặp và chi phí output.

**Bài 21.** Chi phí partition một lượt Grace join hai input R,S, bỏ partial pages?

**Đáp án:** Khoảng `2(N_R+N_S)/B` I/O (một read và một write mỗi record).

**Bài 22.** Chi phí thêm của build/probe đọc lại các partition, bỏ output?

**Đáp án:** Khoảng `(N_R+N_S)/B`.

**Bài 23.** Chi phí join ba pha cơ bản, chưa xuất Z cặp?

**Đáp án:** Khoảng `3(N_R+N_S)/B`, khi các bucket fit và bỏ overhead.

**Bài 24.** Nếu output có Z record và ghi ra disk, thêm khoảng bao nhiêu I/O?

**Đáp án:** `ceil(Z/B)` block writes, cùng overhead nếu page cuối.

**Bài 25.** Nếu N=1.000.000, M_work=50.000, số bucket tối thiểu về **trung bình**?

**Đáp án:** `ceil(1,000,000/50,000)=20`, nhưng vẫn phải kiểm tra skew thực tế.

**Bài 26.** M=100.000, B=1000, fan-out tối đa lý tưởng theo một input buffer?

**Đáp án:** `floor(100000/1000)-1=99`.

**Bài 27.** N=1.000.000, F=20, bucket size trung bình khi hash đều?

**Đáp án:** 50.000 record/bucket.

**Bài 28.** Trung bình bucket 50.000 và M_work=80.000 có chứng minh mọi bucket fit không?

**Đáp án:** Không; bucket lớn có thể vượt 80.000 do skew/collision.

**Bài 29.** Sau d lượt phân hoạch đều F-way, kích thước bucket trung bình khoảng gì?

**Đáp án:** `N/F^d`.

**Bài 30.** Nếu repartition không giảm kích thước bucket, nên làm gì?

**Đáp án:** Detect stall/giới hạn depth; đổi hash hợp lý hoặc fallback skew-aware/sort-based, không lặp vô hạn.

**Bài 31.** Điều kiện bộ nhớ của hash join build bucket là số nhóm hay số record?

**Đáp án:** Tổng bộ nhớ cho những record/payload build và hash table; không chỉ số nhóm, trừ bài toán chỉ cần count.

**Bài 32.** Với GROUP BY SUM, việc combine cục bộ có thể giảm chi phí gì?

**Đáp án:** Giảm lượng record trung gian phải ghi, nhờ gộp các partial sums trước khi spill.

**Bài 33.** Nếu R,S có cùng key nhưng khác hash salt làm khác bucket, hậu quả?

**Đáp án:** Có thể bỏ sót cặp join, sai correctness.

**Bài 34.** Mã Java demo có thật sự dùng FileChannel để xử lý tập dữ liệu vượt heap không?

**Đáp án:** Không; đó là **virtual-disk simulator** trên heap để đo logical block I/O và kiểm tra bất biến.

**Bài 35.** Vì sao chương trình từ chối build bucket 100 record khi `M−B=16`?

**Đáp án:** Build table vượt ngân sách RAM; cần chọn thuật toán fallback hoặc chia lại thích hợp.

**Bài 36.** Trong ví dụ key nặng 100 record nhưng chỉ một khóa, GROUP BY SUM có thể xử lý không?

**Đáp án:** Có, dùng một aggregate entry và quét tuần tự record.

**Bài 37.** Hãy nêu hai loại kiểm thử độc lập cho partition.

**Đáp án:** So multiset/tổng group với oracle chính xác; so join cardinality với nested loops, đồng thời kiểm tra cùng key cùng bucket.

**Bài 38.** Tại sao cần tính `SUM_i ceil(N_i/B)` thay vì `ceil(N/B)` cho output?

**Đáp án:** Mỗi partition có page cuối riêng và không thể ghép partial pages của hai partition thành một write logic chung trong thiết kế tệp độc lập.

**Bài 39.** Nếu tất cả dữ liệu và bảng nhóm đã vừa RAM, có cần partition ra disk không?

**Đáp án:** Không bắt buộc; có thể aggregate trực tiếp và tránh I/O ghi tạm.

**Bài 40.** Chi phí CPU và I/O của partition có luôn cùng đơn vị không?

**Đáp án:** Không; CPU tính hash/xử lý record O(N), I/O đếm block reads/writes O(N/B+F) trong một lượt.

## 18. Checklist triển khai và QA

- [ ] Xác định N,M,B, kích thước record thực và ngân sách bộ đệm?
- [ ] Cấu hình F thỏa `(F+1)*B<=M` sau khi chừa overhead?
- [ ] Tất cả record được phát **đúng một lần** tới partition theo key?
- [ ] Cùng key luôn cùng partition, kể cả key âm/khóa ghép?
- [ ] Hai phía R,S của join dùng **cùng** hash/salt/F và equality?
- [ ] Output buffers đủ B record được flush ngay; buffer cuối được flush?
- [ ] Có record count/valid bytes cho partial page cuối?
- [ ] I/O được đếm bằng `ceil(N/B)` và `SUM_i ceil(N_i/B)`?
- [ ] Có đo kích thước partition thực tế, không chỉ tin giá trị trung bình?
- [ ] Cấu trúc pha tiếp theo (group entries hoặc build records) vừa M_work?
- [ ] Nếu quá lớn, có recursive repartition hoặc sort/skew fallback thực sự?
- [ ] Rehash mỗi tầng có salt mới và progress check, không lặp vô hạn?
- [ ] Có xử lý heavy key mà hash(key) không thể chia nhỏ?
- [ ] Join với khóa lặp có phát đủ r×s cặp theo bag semantics?
- [ ] Có tính I/O ghi output join Z record?
- [ ] GROUP BY có so key thật và combine partial aggregates đúng phép toán?
- [ ] Có xét NULL/collation/normalization/serializing key?
- [ ] Có quản lý giới hạn file handles, dung lượng đĩa và metadata?
- [ ] Có checkpoint/commit/cleanup file tạm an toàn khi lỗi I/O/crash?
- [ ] Đã kiểm thử dữ liệu lệch, một khóa nặng, bucket rỗng, record âm và độ dài không chia hết B?
- [ ] Đã chạy oracle exact cho GROUP BY và nested-loop cho join trên dữ liệu nhỏ?
- [ ] Báo rõ mô phỏng logical block I/O hay đo physical SSD I/O?

## Kết luận

**Phân hoạch theo băm** giải quyết sự thiếu RAM bằng cách đổi bài toán “giữ toàn bộ dữ liệu” thành “đọc từng khối, phân phối vào tệp bucket và xử lý từng bucket”. Ba điều cần giữ vững:

1. **Correctness:** Các bản ghi cùng khóa phải đi cùng phân vùng; với equi-join hai phía phải dùng cùng hash và vẫn so key thật khi xử lý.
2. **Memory/I/O:** Cấp một input buffer và F output buffers trong giới hạn M; một lượt partition có `ceil(N/B)` reads và `SUM_i ceil(N_i/B)` writes, gần `2N/B+O(F)` trong mô hình page.
3. **Skew/fallback:** Kích thước bucket trung bình không đảm bảo mọi bucket vừa RAM. Khi quá lớn, phải phân tích nhu cầu cụ thể của toán tử: GROUP BY có thể stream nhiều record cùng khóa với ít group entries, còn hash join có thể cần chunk, repartition khác hoặc sort-merge; một khóa quá nặng không thể được chia nhỏ chỉ bằng `hash(key)`.

Phân hoạch là **công cụ tổ chức I/O** rất hữu ích cho GROUP BY và Grace hash join, nhưng chỉ trở thành thuật toán ngoài bộ nhớ đáng tin khi **bộ đệm, số lần đọc–ghi, tiến triển của repartition, tính đúng với khóa lặp và xử lý spill** được thiết kế rõ ràng. Mã Java trong bài cho phép kiểm tra các bất biến đó bằng thí nghiệm có kết quả chính xác, trước khi xây dựng phiên bản file-backed chạy trên dữ liệu lớn thật sự.
