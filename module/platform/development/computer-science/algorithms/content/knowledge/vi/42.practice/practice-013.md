# So sánh nhiều lời giải trên cùng hợp đồng đầu vào–đầu ra

## 1. Vì sao phải so sánh trên cùng một hợp đồng?

Một đề thuật toán có thể có nhiều lời giải đều đúng, nhưng chúng có thể khác nhau rất nhiều về thời gian, bộ nhớ, khả năng mở rộng và độ phức tạp khi cài đặt. Muốn so sánh công bằng, trước hết phải bảo đảm **mọi lời giải đang giải cùng một bài toán**.

Một lời giải dùng endpoint đóng `[L,R]`, lời giải khác dùng `[L,R)`; một lời giải trả một đáp án bất kỳ, lời giải kia trả vị trí đầu tiên; một lời giải chấp nhận số âm, lời giải kia giả định số không âm. Dù cùng được gọi là “range query”, chúng chưa chắc có cùng hợp đồng.

**Hợp đồng đầu vào–đầu ra (input/output contract)** xác định chính xác:
- Dữ liệu đầu vào, kiểu dữ liệu, miền giá trị và giới hạn kích thước.
- Các thao tác và thứ tự xuất hiện của chúng.
- Ý nghĩa của từng query, bao gồm quy ước chỉ số và endpoint.
- Kết quả cần trả, thứ tự kết quả và cách xử lý trường hợp biên.
- Các giả định bắt buộc để thuật toán đúng.

Sau khi cố định hợp đồng, ta mới có thể hỏi: lời giải nào đúng, nhanh hơn ở workload nào, dùng ít bộ nhớ hơn, dễ bảo trì hơn và có rủi ro triển khai nào?

Bài này dùng cùng một hợp đồng **tính tổng các đoạn trên mảng tĩnh** để so sánh ba cách: quét trực tiếp, prefix sums và Fenwick Tree. Cả ba nhận cùng `long[]`, cùng danh sách query inclusive `[L,R]`, và đều trả một `long[]` theo thứ tự query ban đầu.

## 2. Viết hợp đồng trước khi viết lời giải

Ví dụ hợp đồng được dùng xuyên suốt:

~~~text
Input:
  n: so phan tu, n >= 0
  a: mang long co n phan tu
  q: so query, q >= 0
  queries: q cap (L,R), 0 <= L <= R < n

Operation:
  SUM(L,R) = a[L] + ... + a[R]
  Endpoint inclusive, index 0-based.
  Mang khong thay doi trong khi xu ly.

Output:
  q so long, moi phan tu la ket qua query tuong ung.
  Giu nguyen thu tu query dau vao.

Numeric contract:
  Moi tong doan phai nam trong mien long.
  Neu khong the bao dam, can dung BigInteger hoac
  mo hinh so hoc khac.

Edge cases:
  n=0 chi hop le khi q=0.
  Query sai chi so phai bi tu choi.
~~~

### Những điều phải chốt rõ

- **Inclusive hay half-open?** `[L,R]` gồm cả R; `[L,R)` không gồm R. Công thức và điều kiện hợp lệ khác nhau.
- **0-based hay 1-based?** Cùng một cặp số có thể trỏ tới hai đoạn khác nhau.
- **Static hay có update?** Prefix sums tĩnh không tự hỗ trợ cập nhật nhanh.
- **SET hay ADD?** Thay giá trị khác với cộng delta.
- **Có cần output theo thứ tự input?** Nếu xử lý offline hoặc song song, phải giữ query ID.
- **Kiểu số nào?** Tổng `int` có thể overflow; ví dụ này dùng `long` và yêu cầu tổng nằm trong miền `long`.

Nếu hai chương trình không cùng tuân theo các điều kiện này, so sánh thời gian của chúng không có ý nghĩa.

## 3. Cùng hợp đồng, nhiều chiến lược

Với mảng tĩnh và các query `SUM(L,R)`, có ba ứng viên tự nhiên:

| Lời giải | Ý tưởng | Tiền xử lý | Mỗi query |
| --- | --- | --- | --- |
| Brute force | Cộng từng phần tử trong đoạn | O(1) | O(R−L+1), worst O(n) |
| Prefix sums | Lưu tổng tiền tố | O(n) | O(1) |
| Fenwick Tree | Lưu tổng các khối theo bit | O(n) với linear build | O(log n) |

Cả ba cùng trả đúng q tổng theo thứ tự query. Sự khác biệt nằm ở cách tổ chức dữ liệu và chi phí phải trả.

### Brute force không phải lời giải “xấu” trong mọi trường hợp

Nếu q rất nhỏ hoặc các đoạn thường rất ngắn, quét trực tiếp có thể đủ nhanh và dễ kiểm chứng. Nó không cần cấu trúc phụ O(n). Nếu q lớn và nhiều đoạn dài, tổng số phần tử phải duyệt tăng mạnh.

### Prefix sums phù hợp workload tĩnh

Ta trả trước chi phí O(n) để tạo mảng `prefix`. Sau đó mỗi query dùng hai lần truy cập và một phép trừ. Khi input không thay đổi và có nhiều query, đây thường là lựa chọn đơn giản, nhanh.

### Fenwick Tree có thêm khả năng cập nhật

Fenwick trả range sum bằng hiệu hai prefix sum, mỗi prefix mất O(log n). Nó hỗ trợ point add trong O(log n), nên phù hợp nếu workload sau này có cập nhật điểm. Với hợp đồng tĩnh hiện tại, lợi ích đó chưa được sử dụng và query chậm hơn prefix sums về mặt tiệm cận.

## 4. Lời giải 1: quét trực tiếp từng đoạn

Với mỗi query `[L,R]`, duyệt từ L tới R và cộng:

~~~text
sum = 0
for i = L..R:
    sum += a[i]
answer = sum
~~~

### Độ phức tạp

Một query tốn O(R−L+1). Với q query, tổng chính xác theo độ dài đoạn là:

~~~text
O(sum over queries (R-L+1))
~~~

Cận xấu nhất là O(nq), khi mọi query có thể phủ gần toàn mảng. Bộ nhớ phụ O(1) ngoài mảng kết quả O(q).

### Khi nào brute force hợp lý?

- q nhỏ.
- Đoạn query rất ngắn.
- n nhỏ và cần baseline dễ hiểu.
- Dùng làm oracle để kiểm tra lời giải tối ưu trên input nhỏ.
- Chi phí tiền xử lý không đáng so với số query thực tế.

### Khi nào không hợp lý?

Nếu n và q đều lớn, ví dụ 200.000 query mỗi query phủ phần lớn mảng, số lượt đọc có thể lên tới hàng chục tỷ. Đúng về mặt logic không có nghĩa là đáp ứng time limit.

Brute force là baseline quan trọng: dễ chứng minh, dễ debug và hữu ích cho differential testing. Đừng loại nó khỏi bộ kiểm thử chỉ vì nó không phải lời giải production tối ưu.

## 5. Lời giải 2: prefix sums

Định nghĩa:

~~~text
prefix[0] = 0
prefix[i+1] = prefix[i] + a[i]

SUM(L,R) = prefix[R+1] - prefix[L]
~~~

`prefix[k]` là tổng của k phần tử đầu tiên, tức `a[0]` tới `a[k−1]`.

### Ví dụ

~~~text
a      = [5, -2, 7, 1, 0, 4]
prefix = [0, 5, 3, 10, 11, 11, 15]

SUM(1,4)
= a[1]+a[2]+a[3]+a[4]
= -2+7+1+0
= 6

= prefix[5]-prefix[1]
= 11-5
= 6
~~~

### Vì sao công thức đúng?

`prefix[R+1]` chứa tổng từ `a[0]` đến `a[R]`. `prefix[L]` chứa tổng từ `a[0]` đến `a[L−1]`. Trừ hai phần chung, còn đúng các phần tử từ L đến R.

### Độ phức tạp

- Build: O(n) thời gian.
- Mỗi query: O(1).
- Tổng: O(n+q).
- Bộ nhớ phụ: O(n) cho prefix, cộng O(q) cho output.

### Lưu ý số học

Nếu tổng prefix vượt `long`, phép cộng hoặc trừ có thể overflow và trả kết quả sai. Dùng `long` chỉ đúng khi constraints chứng minh mọi prefix và range sum nằm trong miền `long`. Nếu không, cân nhắc `BigInteger`, checked arithmetic hoặc một biểu diễn phù hợp.

### Update làm thay đổi lựa chọn

Khi `a[i]` đổi, mọi prefix từ i+1 đến n có thể cần cập nhật. Nếu update xen kẽ query, prefix array cơ bản có thể tốn O(n) cho mỗi lần sửa. Khi ấy Fenwick hoặc Segment Tree thường hợp lý hơn.

## 6. Lời giải 3: Fenwick Tree

Fenwick Tree (Binary Indexed Tree) biểu diễn tổng tiền tố bằng các khối có kích thước liên quan tới bit thấp nhất của chỉ số.

Với chỉ số nội bộ 1-based:

~~~text
lowbit(i) = i & (-i)
prefixSum(k):
  total = 0
  while k > 0:
      total += tree[k]
      k -= lowbit(k)
  return total
~~~

Range sum inclusive:

~~~text
SUM(L,R) = prefixSum(R+1) - prefixSum(L)
~~~

### Linear build O(n)

Có thể xây Fenwick trong O(n), không cần gọi point-add O(log n) cho từng phần tử:

~~~text
for i = 1..n:
    tree[i] += a[i-1]
    parent = i + lowbit(i)
    if parent <= n:
        tree[parent] += tree[i]
~~~

Khi xử lý i theo thứ tự tăng, `tree[i]` đã nhận đóng góp từ các con có chỉ số nhỏ hơn; ta truyền khối đó lên parent. Mỗi vị trí được xử lý số lần hằng số.

### Độ phức tạp

- Linear build: O(n).
- Prefix sum: O(log n).
- Range sum: hai prefix sum, vẫn O(log n).
- Point add: O(log n).
- Bộ nhớ phụ: O(n), cộng O(q) cho output.

### Vì sao dùng Fenwick trong bài tĩnh?

Nó là một ứng viên có cùng output contract, và là lựa chọn tốt nếu workload dự kiến có point updates. Nhưng khi hợp đồng chắc chắn static, prefix sums thường có query O(1) và code ngắn hơn. So sánh phải tính đúng workload hiện tại, không cộng lợi ích giả định của update nếu đề không có update.

## 7. Đặt ba lời giải cạnh nhau

| Tiêu chí | Brute force | Prefix sums | Fenwick Tree |
| --- | --- | --- | --- |
| Cùng input/output contract | Có | Có | Có |
| Build | Không | O(n) | O(n) linear |
| Query range sum | O(độ dài đoạn) | O(1) | O(log n) |
| Point update | Không cần cấu trúc | O(n) trong cách cơ bản | O(log n) |
| Bộ nhớ cấu trúc phụ | O(1) | O(n) | O(n) |
| Code | Rất đơn giản | Đơn giản | Nhiều chi tiết hơn |
| Static nhiều query | Có thể chậm | Thường phù hợp nhất | Có overhead query |
| Dynamic point updates | Quét lại dữ liệu | Cập nhật tốn kém | Phù hợp |

### Không so complexity bằng một con số đơn lẻ

Brute force có chi phí phụ thuộc độ dài từng đoạn, không phải lúc nào cũng đúng n. Nếu tất cả query chỉ dài một phần tử, nó có thể rất tốt.

Prefix sums cần build trước. Với q=0, build toàn bộ prefix có thể là công việc không cần thiết. Một chương trình có thể chỉ chọn build khi biết sẽ có đủ query để bù chi phí.

Fenwick có nhiều thao tác bit và truy cập phụ thuộc chỉ số; O(log n) không cho biết latency cụ thể trên mọi máy. Tuy nhiên nó tạo được đường cập nhật hiệu quả khi workload cần.

## 8. Ví dụ chung để đối chiếu

Dùng một input duy nhất:

~~~text
a = [5, -2, 7, 1, 0, 4, -3, 8, 2, -6, 9, 3]

queries:
(0,11)
(0,0)
(2,5)
(4,9)
(7,11)
(3,3)
~~~

Mọi query đều là đoạn đóng `[L,R]`, 0-based. Kết quả kỳ vọng:

| ID | Query | Phép tính | Kết quả |
| ---: | --- | --- | ---: |
| 0 | (0,11) | Toàn bộ mảng | 28 |
| 1 | (0,0) | 5 | 5 |
| 2 | (2,5) | 7+1+0+4 | 12 |
| 3 | (4,9) | 0+4−3+8+2−6 | 5 |
| 4 | (7,11) | 8+2−6+9+3 | 16 |
| 5 | (3,3) | 1 | 1 |

Do cả ba thuật toán cùng thực hiện đúng sáu query trên cùng mảng, output phải là:

~~~text
[28, 5, 12, 5, 16, 1]
~~~

Nếu kết quả của một phương pháp khác, hãy kiểm tra contract và implementation trước khi kết luận thuật toán không phù hợp.

## 9. So sánh số thao tác một cách có trách nhiệm

Chương trình Java ở phần sau đếm một số thao tác có ý nghĩa để làm rõ cách mỗi phương pháp hoạt động.

Với sample:

- Brute force đọc 29 phần tử từ mảng trong sáu query.
- Prefix build đọc 12 phần tử input; sáu query đọc 12 giá trị prefix (hai giá trị mỗi query).
- Fenwick build đọc 12 phần tử input; sáu query thực hiện 17 lần đọc node trong Fenwick Tree.

~~~text
brute query element reads = 29
prefix build input reads = 12
prefix query prefix reads = 12
fenwick build input reads = 12
fenwick query tree-node reads = 17
~~~

### Các counter không cùng một đơn vị chi phí

Một lần đọc `a[i]`, một lần đọc `prefix[k]` và một lần đọc `tree[k]` không nhất thiết có cùng chi phí trên CPU. Các số trên mô tả **cấu trúc công việc** và giúp kiểm tra hành vi code; chúng không phải benchmark và không được cộng tùy tiện thành một điểm hiệu năng.

Build prefix và build Fenwick còn có các lần ghi cấu trúc phụ, phép cộng, truy cập bộ nhớ và overhead khác. Muốn kết luận thời gian, phải benchmark trong điều kiện kiểm soát.

### Tách build và query

Nếu có một triệu query trên cùng một mảng, chi phí build được phân bổ trên nhiều query. Nếu chỉ có một query, chi phí tiền xử lý có thể không đáng. Hãy so:

~~~text
totalCost = buildCost + q * queryCost
~~~

Với workload có update, cộng thêm số update nhân chi phí update; không so query cost một mình.

## 10. Kiểm tra tính đúng trước khi so tốc độ

Mỗi lời giải phải đáp ứng cùng hậu điều kiện:

1. Output có đúng q phần tử.
2. Phần tử output[i] là tổng đúng của `a[L_i..R_i]`.
3. Thứ tự output trùng thứ tự query input.
4. Không sửa mảng input.
5. Query không hợp lệ bị từ chối theo cùng quy tắc.
6. Kết quả không overflow theo numeric contract.

### Chứng minh ngắn

**Brute force:** vòng lặp cộng lần lượt từng phần tử từ L đến R, nên cộng đúng mỗi phần tử của đoạn một lần.

**Prefix sums:** hiệu `prefix[R+1]−prefix[L]` loại bỏ phần prefix chung `[0,L)`, còn đúng `[L,R]`.

**Fenwick:** cấu trúc phân rã prefix thành các khối không giao nhau; `prefixSum(k)` cộng đủ các khối phủ `[0,k)`. Hiệu hai prefix cho đúng đoạn `[L,R]`.

### Differential testing

Chạy ba lời giải trên cùng dữ liệu và so output từng phần tử. Nếu có khác biệt, brute force trên input nhỏ là oracle dễ hiểu để xác định lỗi ở prefix/Fenwick.

Đừng dùng duy nhất một sample. Duplicate, số âm, mảng rỗng, đoạn một phần tử, đoạn toàn mảng và giá trị lớn đều cần được kiểm tra.

## 11. Java 17: ba lời giải cùng một API

Chương trình sau dùng một kiểu `Query(left,right)` cho cả ba phương pháp. Mỗi phương pháp trả một `Execution` chứa `long[] answers` và hai counter có ý nghĩa riêng: số input reads trong build và số cấu trúc được đọc khi trả query.

- `bruteForce` không build cấu trúc; query đọc từng phần tử.
- `prefixSums` build prefix array một lần; query đọc hai prefix.
- `fenwick` build tree tuyến tính; query đọc các node cần cho hai prefix.
- `verifyExhaustive` liệt kê tất cả mảng có độ dài 0..6, phần tử thuộc −2..2, rồi thử toàn bộ đoạn `[L,R]`.
- `rejectsInvalidRange` xác nhận cả ba cách từ chối query sai.

Lưu mã thành `CompareRangeSumSolutions.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class CompareRangeSumSolutions {

    record Query(int left, int right) {}

    record Execution(
            long[] answers,
            long buildInputReads,
            long queryStructureReads) {}

    record Verification(
            int arraysChecked,
            long queriesChecked) {}

    private static void validate(
            long[] data, List<Query> queries) {
        Objects.requireNonNull(data, "data");
        Objects.requireNonNull(queries, "queries");

        for (Query query : queries) {
            Objects.requireNonNull(query, "query");
            if (query.left() < 0
                    || query.right() < query.left()
                    || query.right() >= data.length) {
                throw new IllegalArgumentException(
                        "query range out of bounds");
            }
        }
    }

    // Candidate 1: direct scan for every inclusive range.
    static Execution bruteForce(
            long[] data, List<Query> queries) {
        validate(data, queries);
        long[] answers = new long[queries.size()];
        long visits = 0L;

        for (int q = 0; q < queries.size(); q++) {
            Query query = queries.get(q);
            long sum = 0L;
            for (int i = query.left();
                    i <= query.right(); i++) {
                sum += data[i];
                visits++;
            }
            answers[q] = sum;
        }
        return new Execution(answers, 0L, visits);
    }

    // Candidate 2: O(n) prefix construction, O(1) per query.
    static Execution prefixSums(
            long[] data, List<Query> queries) {
        validate(data, queries);
        long[] prefix = new long[data.length + 1];
        long buildReads = 0L;

        for (int i = 0; i < data.length; i++) {
            prefix[i + 1] = prefix[i] + data[i];
            buildReads++;
        }

        long[] answers = new long[queries.size()];
        long queryReads = 0L;
        for (int q = 0; q < queries.size(); q++) {
            Query query = queries.get(q);
            answers[q] = prefix[query.right() + 1]
                    - prefix[query.left()];
            queryReads += 2L;
        }
        return new Execution(
                answers, buildReads, queryReads);
    }

    private static final class FenwickTree {
        private final long[] tree;
        private long nodeReads;

        FenwickTree(long[] data) {
            tree = new long[data.length + 1];

            // Linear O(n) construction.
            for (int i = 1; i <= data.length; i++) {
                tree[i] += data[i - 1];
                int parent = i + (i & -i);
                if (parent <= data.length) {
                    tree[parent] += tree[i];
                }
            }
        }

        // Sum of the first count elements: [0,count).
        long prefixSum(int count) {
            long total = 0L;
            for (int i = count; i > 0; i -= i & -i) {
                total += tree[i];
                nodeReads++;
            }
            return total;
        }

        long rangeSum(int left, int right) {
            return prefixSum(right + 1)
                    - prefixSum(left);
        }

        long nodeReads() {
            return nodeReads;
        }
    }

    // Candidate 3: O(n) build, O(log n) per range query.
    static Execution fenwick(
            long[] data, List<Query> queries) {
        validate(data, queries);
        FenwickTree tree = new FenwickTree(data);
        long[] answers = new long[queries.size()];

        for (int q = 0; q < queries.size(); q++) {
            Query query = queries.get(q);
            answers[q] = tree.rangeSum(
                    query.left(), query.right());
        }
        return new Execution(
                answers, data.length, tree.nodeReads());
    }

    private static List<Query> allRanges(int n) {
        List<Query> queries = new ArrayList<>();
        for (int left = 0; left < n; left++) {
            for (int right = left; right < n; right++) {
                queries.add(new Query(left, right));
            }
        }
        return List.copyOf(queries);
    }

    private static Verification verifyExhaustive() {
        int arraysChecked = 0;
        long queriesChecked = 0L;

        // Every array of length 0..6 over {-2,-1,0,1,2}.
        for (int n = 0; n <= 6; n++) {
            int configurations = 1;
            for (int i = 0; i < n; i++) {
                configurations *= 5;
            }

            for (int code = 0; code < configurations; code++) {
                long[] data = new long[n];
                int remaining = code;
                for (int i = 0; i < n; i++) {
                    data[i] = remaining % 5 - 2;
                    remaining /= 5;
                }

                List<Query> queries = allRanges(n);
                Execution brute = bruteForce(data, queries);
                Execution prefix = prefixSums(data, queries);
                Execution bit = fenwick(data, queries);

                if (!Arrays.equals(
                            brute.answers(), prefix.answers())
                        || !Arrays.equals(
                            brute.answers(), bit.answers())) {
                    throw new AssertionError(
                            "candidate answers differ");
                }

                arraysChecked++;
                queriesChecked += queries.size();
            }
        }
        return new Verification(
                arraysChecked, queriesChecked);
    }

    private static boolean rejectsInvalidRange() {
        long[] one = {1L};
        List<Query> invalid = List.of(new Query(0, 1));

        try {
            bruteForce(one, invalid);
            return false;
        } catch (IllegalArgumentException expected) {
            // Expected.
        }

        try {
            prefixSums(one, invalid);
            return false;
        } catch (IllegalArgumentException expected) {
            // Expected.
        }

        try {
            fenwick(one, invalid);
            return false;
        } catch (IllegalArgumentException expected) {
            // Expected.
        }
        return true;
    }

    private static boolean supportsEmptyInput() {
        long[] empty = {};
        List<Query> noQueries = List.of();

        Execution brute = bruteForce(empty, noQueries);
        Execution prefix = prefixSums(empty, noQueries);
        Execution bit = fenwick(empty, noQueries);

        return brute.answers().length == 0
                && prefix.answers().length == 0
                && bit.answers().length == 0;
    }

    public static void main(String[] args) {
        long[] data = {
                5, -2, 7, 1, 0, 4,
                -3, 8, 2, -6, 9, 3
        };
        List<Query> queries = List.of(
                new Query(0, 11),
                new Query(0, 0),
                new Query(2, 5),
                new Query(4, 9),
                new Query(7, 11),
                new Query(3, 3)
        );
        long[] original = data.clone();

        Execution brute = bruteForce(data, queries);
        Execution prefix = prefixSums(data, queries);
        Execution bit = fenwick(data, queries);

        boolean same = Arrays.equals(
                brute.answers(), prefix.answers())
                && Arrays.equals(
                brute.answers(), bit.answers());

        System.out.println("input n = " + data.length);
        System.out.println("query count = " + queries.size());
        System.out.println(
                "brute answers = "
                + Arrays.toString(brute.answers()));
        System.out.println(
                "prefix answers = "
                + Arrays.toString(prefix.answers()));
        System.out.println(
                "fenwick answers = "
                + Arrays.toString(bit.answers()));
        System.out.println("all answers equal = " + same);
        System.out.println(
                "input unchanged = "
                + Arrays.equals(original, data));

        System.out.println(
                "brute query element reads = "
                + brute.queryStructureReads());
        System.out.println(
                "prefix build input reads = "
                + prefix.buildInputReads());
        System.out.println(
                "prefix query prefix reads = "
                + prefix.queryStructureReads());
        System.out.println(
                "fenwick build input reads = "
                + bit.buildInputReads());
        System.out.println(
                "fenwick query tree-node reads = "
                + bit.queryStructureReads());

        System.out.println(
                "empty input supported = "
                + supportsEmptyInput());
        System.out.println(
                "invalid range rejected = "
                + rejectsInvalidRange());

        Verification verification = verifyExhaustive();
        System.out.println(
                "exhaustive arrays checked = "
                + verification.arraysChecked());
        System.out.println(
                "exhaustive range queries checked = "
                + verification.queriesChecked());

        if (!same
                || !Arrays.equals(
                        brute.answers(), new long[] {
                                28, 5, 12, 5, 16, 1
                        })
                || !Arrays.equals(original, data)
                || !supportsEmptyInput()
                || !rejectsInvalidRange()
                || verification.arraysChecked() != 19531
                || verification.queriesChecked() != 382080) {
            throw new AssertionError("validation failed");
        }
        System.out.println("all checks passed = true");
    }
}
~~~

## 12. Biên dịch, chạy và stdout dự kiến

Biên dịch bằng Java 17:

~~~bash
javac CompareRangeSumSolutions.java
java CompareRangeSumSolutions
~~~

Stdout chính xác:

~~~text
input n = 12
query count = 6
brute answers = [28, 5, 12, 5, 16, 1]
prefix answers = [28, 5, 12, 5, 16, 1]
fenwick answers = [28, 5, 12, 5, 16, 1]
all answers equal = true
input unchanged = true
brute query element reads = 29
prefix build input reads = 12
prefix query prefix reads = 12
fenwick build input reads = 12
fenwick query tree-node reads = 17
empty input supported = true
invalid range rejected = true
exhaustive arrays checked = 19531
exhaustive range queries checked = 382080
all checks passed = true
~~~

Các counter là số lần đọc theo đúng vị trí code tăng biến đếm. Chúng làm kết quả tái lập và có thể kiểm lại bằng tay. Chúng **không phải số chu kỳ CPU**, không đo cache miss và không thay benchmark.

### Vì sao test exhaustive có đúng số lượng này?

Số mảng độ dài n trên alphabet 5 giá trị là `5^n`. Tổng với n=0..6:

~~~text
1 + 5 + 25 + 125 + 625 + 3125 + 15625
= 19531 arrays
~~~

Một mảng độ dài n có `n(n+1)/2` đoạn đóng không rỗng. Tổng số query được thử trên toàn bộ các mảng:

~~~text
5*1 + 25*3 + 125*6 + 625*10
+ 3125*15 + 15625*21
= 382080 queries
~~~

Mảng rỗng có 0 query hợp lệ. Với mỗi mảng, cả ba phương pháp phải trả cùng một mảng kết quả.

## 13. Đánh giá complexity theo workload thực tế

### Khi q nhỏ

Nếu chỉ có một query, brute force có thể rẻ hơn build O(n) prefix hoặc Fenwick. Nếu đoạn ngắn, số phần tử thực sự đọc còn ít hơn n. Chọn theo q và độ dài query, không chỉ theo n.

### Khi q lớn và input static

Prefix sums thường thắng về mô hình chi phí: O(n+q), mỗi query O(1). Build được chia sẻ cho toàn bộ query. Đây là ứng viên mặc định mạnh cho nhiều range sum trên dữ liệu bất biến.

### Khi có point update

Nếu hợp đồng mở rộng thành:

~~~text
ADD(i, delta)
SUM(L,R)
ADD(i, delta)
SUM(L,R)
...
~~~

Fenwick có update O(log n), query O(log n). Prefix array cơ bản cần cập nhật O(n) hoặc phải xây lại. Khi workload dynamic, Fenwick có thể là lựa chọn phù hợp hơn dù query đơn lẻ chậm hơn prefix.

### Khi cần nhiều loại query

Nếu cần sum, min, max, assignment hoặc range updates, Segment Tree có thể phù hợp hơn. Không chọn Fenwick chỉ vì một loại thao tác có vẻ giống tổng tiền tố; hãy xác định phép gộp và update cần hỗ trợ.

### Tổng chi phí

Với build một lần và q query:

~~~text
brute:
  O(sum of queried range lengths)

prefix:
  O(n + q)

Fenwick:
  O(n + q log n)
~~~

Nếu có u point updates:

~~~text
Fenwick:
  O(n + (q+u) log n)  // linear build
~~~

Các biểu thức bỏ qua hằng số và đặc điểm phần cứng, nhưng giúp loại cách làm không thể đáp ứng giới hạn.

## 14. Benchmark công bằng giữa nhiều lời giải

Một benchmark chỉ có giá trị khi các candidate nhận **cùng input, cùng số query, cùng semantics và cùng điều kiện môi trường**.

### Quy trình benchmark

1. Sinh hoặc cố định một bộ dữ liệu; lưu seed và cách tạo.
2. Xác nhận tất cả candidate trả cùng output trước khi đo.
3. Chạy warm-up để JVM biên dịch JIT và ổn định đường thực thi.
4. Đo nhiều lần; dùng phân vị hoặc thống kê phù hợp, không chỉ một mẫu.
5. Giữ cùng JVM, heap settings, máy, phiên bản code và tải nền.
6. Không in log hoặc tạo output console lớn trong vùng đo.
7. Đảm bảo kết quả được tiêu thụ để tránh đo code đã bị tối ưu loại bỏ.
8. Đo cả thời gian build và query; tách riêng khi workload cho phép tái sử dụng cấu trúc.
9. Đo memory/allocations khi đó là ràng buộc của bài.
10. Ghi rõ input distribution và tỷ lệ query/update.

### Vì sao `System.nanoTime()` chưa đủ?

Một vòng đo đơn giản có thể hữu ích khi học, nhưng dễ bị nhiễu bởi JIT, GC, OS scheduling, CPU frequency và cache state. Java Microbenchmark Harness (JMH) giúp kiểm soát warm-up, forks, iterations và consumption tốt hơn cho benchmark nghiêm túc.

### Không benchmark một lời giải với input thuận lợi riêng

Nếu brute chỉ nhận query ngắn còn prefix nhận query dài, so sánh không công bằng. Nếu một phương pháp build một lần còn phương pháp khác build lại cho từng query, phải nói rõ workload và vòng đời cấu trúc.

### Đo những gì?

- Wall-clock latency và throughput.
- Thời gian build/initialization.
- Số phép toán hoặc lượt truy cập có định nghĩa rõ.
- Heap allocation, peak memory, GC.
- CPU/cache/I/O khi có công cụ phù hợp.
- Độ biến thiên qua nhiều lần chạy.

Không kết luận “nhanh hơn 3 lần” từ counter khác đơn vị hoặc một lần chạy.

## 15. Tách correctness, performance và maintainability

Một quyết định tốt phải xem ba chiều riêng:

**Correctness:** candidate có đáp ứng chính xác contract trên toàn miền input hợp lệ không? Có proof hoặc invariant? Có edge cases và oracle?

**Performance:** tổng build + query + update có phù hợp constraints? Peak memory và allocation có vừa giới hạn? Có bottleneck thực tế nào?

**Maintainability:** code có dễ đọc, dễ sửa, dễ kiểm thử và ít giả định ẩn? API có thể diễn đạt đúng semantics? Độ phức tạp triển khai có xứng đáng với lợi ích?

Một lời giải O(log n) có thể không đáng dùng cho q=3 và n=20. Một lời giải O(nq) có thể không thể chạy khi q,n đều lớn. Không có lựa chọn tốt nếu chưa biết constraints.

### Ma trận quyết định cho ví dụ

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| n nhỏ, q rất ít | Brute force | Code ngắn, không build |
| n lớn, q lớn, không update | Prefix sums | O(1) query |
| Point updates xen kẽ query | Fenwick | Update/query O(log n) |
| Nhiều loại range operations | Segment Tree hoặc cấu trúc chuyên biệt | Hỗ trợ semantics rộng hơn |
| Cần oracle cho test nhỏ | Brute force | Dễ đối chiếu độc lập |

Đây là gợi ý dựa trên contract đã nêu; workload thật có thể khiến lựa chọn đổi.

## 16. Những lỗi thường gặp khi so sánh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Candidate dùng endpoint khác nhau | Kết quả không cùng semantics | Chốt inclusive/half-open |
| Một lời giải trả first match, lời giải kia trả any match | Output contract khác | Định nghĩa rõ output |
| Candidate nhận input khác nhau | Benchmark không công bằng | Dùng cùng fixture |
| Chỉ so thời gian query | Bỏ qua build cost | Đo tổng build + query |
| Bỏ qua update workload | Chọn cấu trúc sai | Liệt kê operation theo thứ tự |
| So O(log n) với O(1) mà bỏ q | Kết luận thiếu ngữ cảnh | Tính tổng chi phí |
| Dùng sample nhỏ làm bằng chứng | Bỏ qua edge cases | Test và proof |
| Chỉ so checksum | Có thể bỏ sót sai lệch | So từng output |
| Dùng `int` cho tổng lớn | Overflow | Chứng minh bound, dùng long |
| Không kiểm mảng input bị sửa | Side effect ẩn | So snapshot trước/sau |
| Không kiểm query order | Trả đáp án lệch ID | Giữ thứ tự/ID |
| Build lại cấu trúc mỗi query | Tăng chi phí giả tạo | Xác định lifecycle |
| Dùng counter khác đơn vị như benchmark | Diễn giải sai | Counter chỉ để chẩn đoán |
| Chạy một lần rồi kết luận | Nhiễu môi trường | Warm-up và lặp |
| Bỏ qua GC/allocation | Runtime khác kỳ vọng | Đo memory |
| Chọn Fenwick khi chỉ cần static RMQ | Không khớp phép gộp | Kiểm algebra |
| Chọn prefix khi có update dày | Update tốn O(n) | Fenwick/Segment Tree |
| Không có brute oracle | Khó tìm bug tối ưu | Differential testing |
| Không xác định overflow semantics | Các candidate có thể khác | Chốt numeric contract |
| Cố chọn một winner cho mọi workload | Quyết định cứng nhắc | Gắn lựa chọn với constraints |

## 17. Bài tập thực hành

1. Viết input/output contract cho bài range sum.
2. Đổi hợp đồng sang endpoint half-open và sửa cả ba lời giải.
3. Nêu vì sao hai contract khác endpoint không thể benchmark trực tiếp.
4. Tính brute visits cho ba query có độ dài 1, 5 và 10.
5. Tính prefix build cost khi q=0.
6. Tìm q tại đó prefix bắt đầu có lợi về mặt mô hình so với scan toàn đoạn.
7. Chứng minh prefix formula cho inclusive `[L,R]`.
8. Chuyển công thức sang half-open `[L,R)`.
9. Xây Fenwick bằng point-add và so với linear build.
10. Chứng minh linear Fenwick build truyền đúng block lên parent.
11. Tính số node Fenwick được đọc cho một prefix.
12. Tại sao range sum cần hai prefix queries?
13. So O(nq) với O(n+q) khi n=q=100.000.
14. So memory của prefix và Fenwick.
15. Thêm point update vào contract rồi chọn lại candidate.
16. Cài `ADD(i,delta)` cho Fenwick.
17. Thử SET bằng cách tính delta từ giá trị cũ.
18. Nêu vì sao prefix array cơ bản cập nhật tốn O(n).
19. Mở rộng sang range minimum và đánh giá prefix min.
20. Vì sao min không có phép trừ prefix?
21. Chọn Segment Tree cho point set + range minimum.
22. Viết brute oracle cho range minimum.
23. Sinh mảng có số âm và duplicate.
24. Kiểm tra tổng có thể overflow int.
25. Chứng minh giới hạn để tổng nằm trong long.
26. Chuyển sang BigInteger khi contract cần tổng chính xác lớn hơn long.
27. Kiểm input rỗng và query rỗng.
28. Kiểm query L<0, R>=n và L>R.
29. Kiểm thứ tự kết quả khi query được sắp xếp offline.
30. Thêm query ID rồi khôi phục output order.
31. Tạo một test mà hai candidate trả khác nhau vì off-by-one.
32. Dùng differential testing để tìm lỗi Fenwick.
33. Tính số mảng độ dài 0..6 trên alphabet 5 giá trị.
34. Tính tổng số đoạn được test là 382.080.
35. Mở rộng exhaustive test lên độ dài 7 và ước lượng công việc.
36. Tạo randomized test với seed cố định.
37. Viết property test cho range sum bằng hiệu prefix.
38. Viết property test cho Fenwick so với brute.
39. Benchmark build riêng và query riêng.
40. Thiết kế warm-up và nhiều iteration cho JVM.
41. Nêu các nguồn nhiễu khi dùng nanoTime.
42. Giải thích vai trò JMH.
43. Vì sao không được cộng các counter khác đơn vị?
44. So throughput và latency cho workload khác nhau.
45. Đo peak heap và allocations.
46. Chọn brute khi q rất nhỏ và giải thích.
47. Chọn prefix khi q lớn, input static.
48. Chọn Fenwick khi có point updates.
49. Chọn Segment Tree khi operation đa dạng.
50. Viết báo cáo so sánh candidate có contract, proof, complexity, test và benchmark.

## 18. Checklist trước khi kết luận lời giải nào tốt hơn

- Mọi candidate có cùng **input/output contract**?
- Endpoint, index base, duplicate và ordering đã thống nhất?
- Static/dynamic, query/update và thứ tự thao tác đã rõ?
- Numeric type và overflow semantics đã được chứng minh?
- Mỗi candidate có cùng input fixture và output semantics?
- Correctness đã được kiểm bằng proof/invariant và oracle?
- Có edge cases, invalid input và exhaustive/random tests?
- Đã tính build cost, query cost và update cost?
- Complexity tổng có đáp ứng n, q và memory limit?
- Đã đo peak memory/allocation khi cần?
- Benchmark có warm-up, nhiều lần chạy và cùng môi trường?
- Counter có được diễn giải đúng đơn vị?
- Lựa chọn cuối có gắn với workload thực tế?
- Code có đủ đơn giản để người khác bảo trì?

**Kết luận:** so sánh nhiều lời giải chỉ có ý nghĩa khi tất cả giải cùng một hợp đồng đầu vào–đầu ra. Chốt semantics và constraints trước, sau đó so correctness, tổng chi phí build/query/update, bộ nhớ, độ phức tạp triển khai và benchmark công bằng. Với range sum tĩnh, brute force là baseline, prefix sums thường phù hợp khi có nhiều query, còn Fenwick hữu ích khi cần point updates. Không có một winner độc lập với workload; quyết định phải dựa trên hợp đồng thật và bằng chứng kiểm thử.
