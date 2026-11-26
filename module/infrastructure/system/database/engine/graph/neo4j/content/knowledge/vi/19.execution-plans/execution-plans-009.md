# So sánh kế hoạch trước và sau thay đổi bằng cùng bộ dữ liệu

Một truy vấn Neo4j có thể cho **cùng kết quả** nhưng tiêu thụ rất khác nhau về số hàng trung gian, lượt truy cập dữ liệu, bộ nhớ và thời gian chạy. Khi thêm **index**, viết lại `WHERE`, thay đổi hướng duyệt quan hệ hoặc điều chỉnh cách tổng hợp trong Cypher, cách kiểm tra đáng tin cậy là **đặt kế hoạch thực thi trước và sau cạnh nhau, với cùng dữ liệu và cùng điều kiện chạy**.

Đây là bài thực hành thuộc chương **Kế hoạch thực thi** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Trong hệ thống property graph, node và relationship được truy vấn bằng Cypher; kỹ thuật đối chiếu kế hoạch dưới đây cũng áp dụng khi tối ưu truy vấn đường đi, phân trang, Java Driver và Spring Data Neo4j. Nội dung dùng cú pháp Neo4j 5 làm tham chiếu. Tên toán tử hoặc chi tiết báo cáo kế hoạch có thể khác nhau giữa các phiên bản và runtime.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **truy vấn logic**, **kế hoạch vật lý** và các số đo thực thi.
2. Thiết lập phép thử **A/B trước–sau** với cùng đồ thị, cùng tham số và cùng kết quả mong đợi.
3. Dùng `EXPLAIN` để so sánh kế hoạch dự kiến, `PROFILE` để xem số hàng và chi phí thực tế.
4. Nhận diện các toán tử thường gặp như `NodeByLabelScan`, `NodeIndexSeek`, `Filter`, `Sort`, `Top`, `Expand(All)` và `EagerAggregation` khi xuất hiện trong kế hoạch.
5. Lập bảng chứng cứ để kết luận thay đổi nào thực sự có ích, nêu rõ giới hạn của lần đo.

## 2. Đọc kế hoạch để trả lời câu hỏi gì?

Cypher mô tả **kết quả cần lấy**. Trình lập kế hoạch Neo4j chọn cách truy cập node, duyệt relationship, lọc, kết hợp, tổng hợp và sắp xếp. Cùng câu lệnh có thể xuất hiện các kế hoạch vật lý khác nhau khi thay đổi thống kê, schema hoặc phiên bản.

| Thành phần | Cho biết điều gì? | Có thể dùng để kết luận gì? |
|---|---|---|
| `EXPLAIN` | Kế hoạch **dự kiến**, ước lượng hàng/chi phí; **không thực thi** truy vấn | Dự kiến dùng scan hay index, có `Sort` hay không, thứ tự các bước |
| `PROFILE` | **Thực thi** truy vấn và gắn các thống kê như `Rows`, `DB Hits` vào kế hoạch | Bao nhiêu hàng đi qua các toán tử; nguồn tốn nhiều lượt truy cập |
| Kết quả truy vấn | Các hàng, cột và giá trị nghiệp vụ | Hai phương án có thực sự tương đương về kết quả không |
| Đo thời gian nhiều lần | Phân bố thời gian trong điều kiện thử nghiệm cụ thể | Thay đổi có cải thiện thời gian quan sát được hay chỉ cải thiện một chỉ số kế hoạch |

**Không lấy “kế hoạch trông đẹp” thay cho kiểm tra kết quả.** Ví dụ, thêm `LIMIT 20` hoặc bỏ một nhánh `MATCH` có thể làm truy vấn rất nhanh nhưng trả thiếu dữ liệu. Ngược lại, ít `DB Hits` thường là tín hiệu tốt, song **không bảo đảm** thời gian chạy thấp hơn trong mọi điều kiện.

## 3. Nguyên tắc so sánh công bằng

Để xác định lợi ích của **một thay đổi**, cần giữ cố định những yếu tố còn lại:

| Yếu tố | Điều kiện trước và sau |
|---|---|
| Đồ thị | Cùng database, cùng tập node/relationship, cùng thuộc tính và giá trị |
| Tham số | Cùng giá trị, **cùng kiểu** (số, chuỗi, `DATE`, `DATETIME`, …) |
| Truy vấn cần so | Giữ nguyên khi chỉ đo tác động của index; thay đúng phần cần kiểm tra khi thử viết lại Cypher |
| Phiên bản/runtime | Giữ cùng Neo4j và môi trường thực thi trong một lượt so sánh |
| Kết quả | Kiểm tra cùng tập hàng, giá trị và thứ tự nếu truy vấn hứa hẹn thứ tự |
| Schema | Khi kiểm tra tác động của index, chỉ index được chọn là biến số chủ động thay đổi |
| Tải hệ thống | Hạn chế giao dịch ghi và truy vấn nặng khác trong lúc đo |
| Bộ nhớ đệm | Làm nóng tương đương; không lấy một lần chạy lạnh so với một lần chạy đã được cache |

Khi thử **thêm index**, dữ liệu đồ thị phải giữ nguyên nhưng schema, cấu trúc index và thống kê liên quan sẽ thay đổi có chủ đích. Khi thử **viết lại câu truy vấn**, giữ nguyên cả dữ liệu lẫn schema, đồng thời chứng minh hai câu Cypher trả cùng kết quả.

Một lần `PROFILE` đủ để khám phá kế hoạch, **chưa đủ** để kết luận ổn định về thời gian. Nên tách bước phân tích kế hoạch với bước đo độ trễ nhiều lần.

## 4. Thiết lập bộ dữ liệu Neo4j cố định

Ví dụ kiểm tra tác động của **range index** trên thuộc tính `orderNo` của `:PlanSampleOrder`. Ta cần đủ nhiều node để dễ thấy khác biệt giữa quét theo label và tìm theo index, nhưng vẫn nhỏ để học trên máy thử nghiệm.

**Chỉ chạy lệnh tạo dữ liệu một lần trong database thực hành riêng.** Nếu chạy lại `CREATE`, bạn tạo thêm node trùng mã và phá điều kiện “cùng bộ dữ liệu”. Không chạy ví dụ trên database sản xuất hoặc nơi có sẵn node dùng cùng nhãn.

~~~cypher
UNWIND range(1, 10000) AS n
CREATE (:PlanSampleOrder {
  orderNo: n,
  amount: 100000 + (n % 20) * 10000,
  createdAt: date('2026-01-01') + duration({days: n % 365}),
  status: CASE WHEN n % 3 = 0 THEN 'PAID' ELSE 'NEW' END
});
~~~

Bộ dữ liệu có 10.000 đơn hàng mô phỏng; `orderNo` là các số nguyên từ `1` đến `10000`, còn giá trị `amount`, `createdAt` và `status` được tính **xác định** từ `n`. Không sử dụng `rand()` hoặc giá trị thời gian hiện tại, vì làm như vậy khiến dữ liệu tạo lại có thể khác.

Ghi lại **dấu vân tay dữ liệu** trước khi bắt đầu:

~~~cypher
MATCH (o:PlanSampleOrder)
RETURN count(o) AS nodeCount,
       count(DISTINCT o.orderNo) AS distinctOrderNos,
       min(o.orderNo) AS minOrderNo,
       max(o.orderNo) AS maxOrderNo,
       sum(o.orderNo) AS sumOrderNo,
       sum(o.amount) AS sumAmount;
~~~

Kết quả mong đợi nếu dữ liệu đúng một lần:

| Chỉ số | Giá trị |
|---|---:|
| `nodeCount` | 10.000 |
| `distinctOrderNos` | 10.000 |
| `minOrderNo` | 1 |
| `maxOrderNo` | 10.000 |
| `sumOrderNo` | 50.005.000 |
| `sumAmount` | 1.950.000.000 |

Các chỉ số này giúp phát hiện nhiều sai sót (như tạo dữ liệu hai lần), nhưng không phải bằng chứng mật mã rằng mọi thuộc tính và relationship đều bất biến. Trong hệ thống thật, hãy dùng thêm tập khóa chính, số relationship, thống kê theo loại và kiểm soát không có giao dịch ghi trong giai đoạn đo.

### Đặt một truy vấn mục tiêu

Tìm tối đa 20 đơn hàng có mã trong phạm vi `[8500, 8600)`, tăng dần theo mã:

~~~cypher
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500 AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

Kết quả đúng gồm **20 hàng** với `orderNo` từ `8500` đến `8519`. `orderNo` duy nhất trong dữ liệu mẫu nên thứ tự xác định rõ; điều này giúp đối chiếu kết quả trước và sau. Nếu phép thử dùng dữ liệu có các khóa sắp xếp trùng nhau, cần thêm khóa phụ để kiểm tra thứ tự ổn định.

## 5. Bước A: thu thập kế hoạch **trước** khi tạo index

Trước tiên, đảm bảo database thực hành **chưa có property index tương đương** trên `:PlanSampleOrder(orderNo)`. Dùng:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

Nếu đã có index thích hợp trên nhãn và thuộc tính này, phép đo “trước khi tạo index” không còn nguyên vẹn. Hãy thực hiện trong database thử nghiệm mới hoặc tiếp tục như một phép so sánh **viết lại truy vấn với schema cố định**. Không xóa index đang phục vụ ứng dụng thật chỉ để tái hiện bài học.

Chạy `EXPLAIN`:

~~~cypher
EXPLAIN
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500 AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

Khi chưa có index phù hợp, một kế hoạch hợp lý có thể quét các node mang nhãn `PlanSampleOrder`, kiểm tra `orderNo`, rồi xử lý sắp xếp/giới hạn. **Không cố đoán tên hoặc thứ tự toán tử chính xác** vì trình tối ưu có thể gộp, biến đổi hoặc thay toán tử theo runtime.

Tiếp tục chạy `PROFILE` với **cùng truy vấn**:

~~~cypher
PROFILE
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500 AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

Lưu lại ảnh chụp hoặc bản ghi các trường sau từ kế hoạch trong Neo4j Browser hay công cụ truy vấn:

1. **Toán tử bắt đầu truy cập dữ liệu**, ví dụ quét node theo label hay dùng index.
2. **`Rows` ở từng toán tử**: số hàng được tạo, lọc và truyền lên bước sau.
3. **`DB Hits`**, kèm dữ liệu truy cập thực tế nếu công cụ hiển thị.
4. **`Sort`/`Top`, `Filter`**: các bước xử lý còn cần sau khi lấy node.
5. **Kết quả trả về**: 20 hàng, `orderNo` 8500–8519, giá trị `amount` đúng.

Nếu `PROFILE` hiển thị thời gian, chỉ ghi là **số đo của lần chạy đó**. Không tự coi đây là thời gian đại diện cho mọi lượt.

## 6. Bước B: thêm index nhưng giữ **nguyên dữ liệu**

Tạo đúng một index để phục vụ điều kiện phạm vi:

~~~cypher
CREATE RANGE INDEX plan_sample_order_no_idx IF NOT EXISTS
FOR (o:PlanSampleOrder) ON (o.orderNo);
~~~

Theo dõi index cho đến khi `state = 'ONLINE'`:

~~~cypher
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties, state
WHERE name = 'plan_sample_order_no_idx'
RETURN name, type, labelsOrTypes, properties, state;
~~~

Index mới có thể ở trạng thái `POPULATING` trong lúc xây dựng. Nếu không thấy index như mong đợi, cần kiểm tra tên và schema thực tế; nếu `FAILED`, khắc phục lỗi trước khi đo. `IF NOT EXISTS` tránh một số lỗi tạo trùng nhưng không thay việc kiểm tra index thật.

**Chạy lại truy vấn dấu vân tay ở mục 4.** Các chỉ số `nodeCount`, `distinctOrderNos`, `minOrderNo`, `maxOrderNo`, `sumOrderNo` và `sumAmount` phải giữ nguyên vì thao tác tạo index không thêm/sửa/xóa các node trong bộ dữ liệu.

Sau khi index `ONLINE`, chạy lại **nguyên văn** hai lệnh `EXPLAIN` và `PROFILE` ở bước A. Không thêm hint, không đổi khoảng `8500–8600`, không chỉnh `LIMIT` hay `ORDER BY`. Đây là điều kiện quan trọng để quy kết thay đổi kế hoạch cho index.

Kế hoạch sau có thể xuất hiện một toán tử như `NodeIndexSeekByRange` hoặc `NodeIndexSeek` để tìm node theo khoảng `orderNo`; trình tối ưu cũng có thể tận dụng thứ tự khóa index cho `ORDER BY orderNo ASC` và `LIMIT 20`. Tuy nhiên, **không bảo đảm** nó luôn bỏ `Sort` hoặc nhất định chọn index: quy tắc chi phí, thống kê và kích thước dữ liệu quyết định kế hoạch thực tế.

### Minh họa đường đi dữ liệu

~~~mermaid
flowchart LR
    subgraph Before["Trước: không có index phù hợp"]
        A["Quét node :PlanSampleOrder"] --> B["Lọc orderNo trong khoảng"]
        B --> C["Sắp xếp / lấy 20 hàng"]
    end
    subgraph After["Sau: index đã ONLINE"]
        D["Range index trên orderNo"] --> E["Tìm giá trị 8500..8599"]
        E --> F["Lấy 20 hàng theo thứ tự"]
    end
~~~

Sơ đồ minh họa **phương án có thể được chọn**, không phải bản chép một kế hoạch `PROFILE` đã đo trên database thật.

## 7. So sánh kế hoạch trước–sau bằng bảng chứng cứ

Không có dữ liệu chạy thực tế trong bài học này nên bảng dưới đây là **mẫu để người học điền**, không phải kết quả đo đã được xác nhận:

| Tiêu chí | Trước: chưa có range index | Sau: đã có range index |
|---|---|---|
| Số node trong graph | 10.000 (xác nhận bằng truy vấn) | 10.000 (kiểm tra lại) |
| Kết quả `orderNo` | 8500–8519 | 8500–8519 |
| Toán tử đọc dữ liệu | *Ghi từ `PROFILE`* | *Ghi từ `PROFILE`* |
| `Rows` tại toán tử đọc | *Điền số quan sát* | *Điền số quan sát* |
| Tổng `DB Hits` | *Điền số quan sát* | *Điền số quan sát* |
| Có `Sort` hoặc `Top`? | *Điền theo kế hoạch* | *Điền theo kế hoạch* |
| Thời gian chạy sau warm-up | *Đo nhiều lượt* | *Đo nhiều lượt* |
| Kết luận | *Dựa trên dữ liệu thu thập* | *Nêu lợi ích và giới hạn* |

Một ví dụ **giả định** về cách đọc bảng: nếu trước khi thêm index kế hoạch phải xem xét 10.000 node, còn sau index chỉ truy cập phạm vi 100 khóa rồi trả 20 hàng, đó là dấu hiệu giảm việc quét dữ liệu. Con số `Rows` hoặc `DB Hits` cụ thể phải lấy từ `PROFILE`, bởi một toán tử có thể dừng sớm, đọc cache, hoặc trả dữ liệu theo cách khác dự đoán.

### Những toán tử nên chú ý

| Toán tử (tên có thể khác theo phiên bản) | Vai trò thường gặp | Câu hỏi khi so sánh |
|---|---|---|
| `NodeByLabelScan` | Duyệt node theo label | Có đang quét tập lớn để lọc ít kết quả? |
| `NodeIndexSeek` / `NodeIndexSeekByRange` | Tra cứu từ property index | Index có phù hợp điều kiện và đủ chọn lọc? |
| `NodeIndexScan` | Đọc các entry của index | Có tận dụng thứ tự hoặc chỉ quét một phần lớn index? |
| `Filter` | Loại hàng sau bước trước | Bao nhiêu hàng bị loại; có thể đẩy điều kiện sớm hơn? |
| `Sort` / `Top` | Sắp xếp toàn bộ hoặc duy trì tập kết quả đầu | Có thể tránh sắp xếp bằng index hoặc giảm số hàng trước khi sắp? |
| `Expand(All)` / `Expand(Into)` | Duyệt relationship giữa node | Nhánh quan hệ nào đang làm số hàng tăng mạnh? |
| `EagerAggregation` | Gom nhóm/tổng hợp có ranh giới thực thi | Đang xử lý bao nhiêu hàng trước khi gom nhóm? |

**`Rows` không đồng nghĩa số node khác nhau.** Một node có thể xuất hiện trong nhiều hàng khi mở rộng nhiều relationship. Tương tự, **`DB Hits` không đồng nghĩa số lần đọc đĩa**: đó là thước đo truy cập lớp dữ liệu trong kế hoạch, chịu ảnh hưởng của thao tác và runtime. Hãy đánh giá nó cùng số hàng, CPU, bộ nhớ và thời gian, thay vì so sánh từng chỉ số một cách tách rời.

## 8. Thí nghiệm thứ hai: viết lại truy vấn, **giữ nguyên index**

Sau bước B, giữ nguyên database và index `plan_sample_order_no_idx`. Thử hai dạng lọc tương đương **trên dữ liệu mẫu đã xác nhận `orderNo` là INTEGER**.

**Biến thể C — biến đổi thuộc tính trong điều kiện:**

~~~cypher
PROFILE
MATCH (o:PlanSampleOrder)
WHERE toInteger(o.orderNo) >= 8500
  AND toInteger(o.orderNo) < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

**Biến thể D — so sánh trực tiếp thuộc tính:**

~~~cypher
PROFILE
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500
  AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

`toInteger(o.orderNo)` không thay đổi giá trị số nguyên của các node mẫu, nhưng việc bọc thuộc tính bằng hàm có thể làm bộ tối ưu khó biến điều kiện thành phép tra cứu trực tiếp trên index `orderNo`. Dạng D thường là một ứng viên tốt hơn để dùng range index. **Đây là giả thuyết cần kiểm bằng `PROFILE`**, không phải cam kết mọi phiên bản sẽ tạo kế hoạch khác.

Hai truy vấn chỉ tương đương khi kiểu và giá trị dữ liệu phù hợp. Nếu có dữ liệu chuỗi, giá trị không chuyển được sang số hoặc `null`, phép chuyển kiểu có thể làm thay đổi ngữ nghĩa. Trước khi dùng kỹ thuật viết lại trong ứng dụng thật, cần kiểm tra lược đồ và dữ liệu thực tế.

Ở thí nghiệm này **không thay index, dữ liệu, `RETURN`, `ORDER BY` hay `LIMIT`**. So sánh số hàng kết quả bằng tập `orderNo` và `amount`; kế đó so toán tử, `Rows`, `DB Hits` và thời gian nhiều lượt. Nếu cả hai dùng cùng kế hoạch, hãy ghi nhận trung thực rằng tối ưu hóa này **không tạo khác biệt đo được trong môi trường thử nghiệm**.

## 9. Khi so sánh truy vấn đồ thị có relationship

Truy vấn theo đường đi thường có thêm yếu tố **nhân số hàng khi mở rộng relationship**. Ví dụ, một khách hàng có nhiều đơn hàng và nhiều đánh giá:

~~~cypher
MATCH (c:Customer)
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       count(o) AS orderCount,
       count(r) AS reviewCount;
~~~

Với `m` đơn hàng và `n` đánh giá, truy vấn có thể tạo `m × n` hàng cho mỗi khách hàng rồi tổng hợp. Kế hoạch có thể cho thấy `Rows` tăng tại các bước mở rộng. Nếu yêu cầu nghiệp vụ thực sự là đếm **số đơn hàng** và **số đánh giá** độc lập, câu truy vấn trên còn có khả năng **sai kết quả**, không chỉ chậm.

Trong Neo4j 5.23 trở lên, có thể thử phiên bản tổng hợp tách nhánh:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId, orderCount, reviewCount;
~~~

**Cẩn thận về tính công bằng:** hai ví dụ vừa rồi không phải cặp A/B tương đương nếu khách hàng có nhiều bản ghi trên cả hai nhánh. Trước khi dùng chúng để so thời gian, phải **sửa truy vấn gốc để cùng đúng về kết quả** (chẳng hạn dùng `count(DISTINCT ...)` cho hai phép đếm node phù hợp với nghiệp vụ), hoặc xác định đây là **thay đổi vừa sửa lỗi logic vừa thay đổi kế hoạch**. Không báo cải thiện hiệu năng của một câu truy vấn sai số liệu như thành tích tối ưu hóa đơn thuần.

Với các truy vấn liên kết phức tạp, hãy quan sát:

- `Rows` **trước và sau** toán tử mở rộng relationship: số hàng có tăng theo cấp số nhân không?
- `DB Hits` tại các bước duyệt cạnh: biến đầu vào có đủ chọn lọc để bắt đầu từ node phù hợp không?
- Vị trí tổng hợp và lọc: liệu điều kiện có thể đặt sớm hơn mà **không đổi kết quả**?
- Điều kiện nhận diện node: một biến node bị lặp theo số đường đi có cần `DISTINCT` hay không?

## 10. Đo thời gian mà không tự đánh lừa mình

`PROFILE` giúp đọc hoạt động bên trong, nhưng số đo độ trễ của một lần gọi có thể bị nhiễu bởi cache, JIT, tài nguyên máy, mạng và các truy vấn đồng thời. Để đánh giá trước–sau:

1. **Khóa biến số:** cùng database, dữ liệu, phiên bản, tham số và số hàng đầu ra; ghi rõ thay đổi schema hay câu Cypher.
2. **Xác minh index `ONLINE`** trước khi đo phương án có index.
3. **Làm nóng tương đương:** chạy một số lượt trước khi lấy số đo chính thức; nếu chạy A rồi B trong cùng phiên, B có thể hưởng lợi từ page cache đã nóng.
4. **Chạy lặp lại nhiều lượt** trên cùng workload, có thể luân phiên A/B khi so hai truy vấn có cùng schema; ghi trung vị và khoảng dao động thay vì chỉ một lần nhanh nhất.
5. **Đo cả kế hoạch lẫn latency:** dùng `PROFILE` để tìm khác biệt `Rows`/`DB Hits`, dùng việc đo thời gian riêng để tránh chi phí profiling trở thành yếu tố gây nhiễu.
6. **Kiểm tra số hàng, giá trị, thứ tự** sau mỗi thay đổi; với các phép tổng hợp, đối chiếu cả các trường hợp 0, 1 và nhiều quan hệ.

Trong ứng dụng Java Driver, truyền cùng tham số có kiểu rõ ràng và đo cùng phương thức đọc (cùng transaction mode, fetch size, routing và điều kiện mạng). Nếu dùng Spring Data Neo4j, chú ý truy vấn mà framework thực sự gửi và các bước chuyển đổi/mapping kết quả. Thời gian nhìn từ ứng dụng còn gồm kết nối, truyền dữ liệu và mapping, nên có thể khác với thời gian trên Neo4j Browser.

### Vì sao nên nhìn phân bố thay vì một số đơn lẻ?

Giả sử một lần đo sau thay đổi nhanh hơn, nhưng các lần sau lại chậm hơn; không thể kết luận đã cải thiện ổn định. Với một mẫu nhỏ, hãy ghi **trung vị**, giá trị chậm bất thường và điều kiện tải. Với hệ thống thật, chọn thêm phân vị như `p95` và theo dõi tác động đến truy vấn ghi nếu thay đổi là thêm index.

## 11. Những lỗi phương pháp phổ biến

| Lỗi | Vì sao làm sai kết luận? | Cách khắc phục |
|---|---|---|
| Chạy lại lệnh tạo dữ liệu giữa hai lần đo | Khác kích thước hoặc phân bố dữ liệu | Tạo một lần; so dấu vân tay trước/sau |
| Đổi tham số hoặc kiểu dữ liệu | Độ chọn lọc và kế hoạch có thể khác | Khóa cùng tham số và kiểu |
| So `PROFILE` lạnh với lần chạy đã làm nóng cache | Tốc độ chịu ảnh hưởng cache | Warm-up tương đương, lặp nhiều lần |
| So truy vấn trả 100 hàng với truy vấn chỉ trả 20 hàng | Hai yêu cầu khác nhau | Chứng minh cùng tập kết quả mong đợi |
| `ORDER BY` thiếu khóa phụ trong trường hợp đồng giá | Các hàng bị trùng khóa có thể đổi chỗ | Thêm khóa ổn định khi nghiệp vụ yêu cầu |
| Tạo index nhưng đo lúc `POPULATING` | Index chưa sẵn sàng | Xác nhận `ONLINE` |
| Tạo nhiều index, thay truy vấn và thay runtime cùng lúc | Không biết thay đổi nào tạo tác động | Tách từng thí nghiệm có đối chứng |
| Đếm `DB Hits` rồi coi như thời gian đĩa hoặc tốc độ tuyệt đối | Chỉ số khác lớp đo | Đọc nhiều chỉ số và đo latency riêng |
| Tự suy ra phải có `NodeIndexSeek` | Optimizer có thể chọn kế hoạch khác | Đọc `EXPLAIN`/`PROFILE` cụ thể |
| Kết luận từ bộ dữ liệu cực nhỏ | Scan có thể rẻ hơn index | Kiểm tra trên dữ liệu đại diện |

Đừng xóa index của ứng dụng hoặc thay đổi schema sản xuất chỉ để tái hiện bài học. Mẫu thí nghiệm nên chạy trên môi trường riêng, có kiểm soát tải và không chứa các giao dịch sản xuất.

## 12. Mẫu biên bản so sánh có thể dùng lại

Sao chép khung sau vào ghi chú khi tối ưu một truy vấn Cypher:

~~~text
Mục tiêu nghiệp vụ:
Database / phiên bản Neo4j / runtime:
Ngày đo / tải hệ thống:
Bộ dữ liệu: node, relationship, dấu vân tay:
Tham số (giá trị và kiểu):
Điều kiện trước: schema, truy vấn, index state:
Điều kiện sau: chỉ thay đổi nào?:

KẾT QUẢ ĐÚNG:
  Số hàng trước/sau:
  Khóa và giá trị tổng hợp trước/sau:
  ORDER BY và thứ tự trước/sau:

KẾ HOẠCH EXPLAIN/PROFILE:
  Toán tử đọc dữ liệu trước/sau:
  Rows theo các bước quan trọng:
  DB Hits trước/sau:
  Sort/Top, mở rộng quan hệ, tổng hợp:
  Ước lượng so với Rows thực tế:

ĐỘ TRỄ:
  Số lần warm-up / số lần đo:
  Trung vị trước/sau:
  Độ dao động, p95 nếu đủ lượt:

KẾT LUẬN:
  Lợi ích quan sát được:
  Đánh đổi (ghi, dung lượng index, bộ nhớ):
  Giới hạn thử nghiệm / bước xác minh tiếp:
~~~

Báo cáo nên có cả **bằng chứng lẫn giải thích**: “Sau khi thêm range index, kế hoạch chuyển từ bước quét label sang tra cứu theo phạm vi và số `DB Hits` giảm trong phép thử này” là kết luận tốt nếu có số đo tương ứng. Còn “index luôn nhanh hơn” là khẳng định vượt quá dữ liệu đo được.

## 13. Bài tập tự luyện

### Bài 1 — Tự điền bảng kết quả

Thực hiện các bước A và B trong database thực hành riêng. Điền tên toán tử đọc dữ liệu, `Rows`, `DB Hits` và có/không có `Sort` cho từng phương án. Trả lời: Neo4j có dùng range index sau khi tạo không? Nếu không, yếu tố nào trong dữ liệu hoặc kế hoạch có thể giải thích?

**Gợi ý:** kiểm tra trạng thái `ONLINE`, kiểu `orderNo`, số node, bộ lọc, thống kê và kế hoạch thực tế. Không ép kết quả khớp với hình dung ban đầu.

### Bài 2 — Tách hai nguyên nhân

Một đồng nghiệp vừa thêm index trên `createdAt`, vừa đổi bộ lọc từ `date(o.createdAt)` sang `o.createdAt`, sau đó báo “index giúp truy vấn nhanh hơn 60%”. Vì sao chưa thể kết luận? Hãy đề xuất cách thử xác định ảnh hưởng riêng của từng thay đổi.

**Đáp án tham khảo:** đây là hai thay đổi cùng lúc. Giữ nguyên dataset và tham số; đo truy vấn cũ/truy vấn mới **với cùng schema** để đánh giá viết lại câu lệnh. Sau đó giữ nguyên một câu truy vấn và đo trước/sau index trong môi trường có kiểm soát. Phải xác minh `createdAt` thật sự cùng kiểu temporal và ngữ nghĩa hai biểu thức tương đương trên dữ liệu đo.

### Bài 3 — Cùng kế hoạch nhưng thời gian khác nhau

Hai lượt `PROFILE` có cùng toán tử và `DB Hits` gần bằng nhau, nhưng lượt thứ hai chạy nhanh hơn rõ. Có nhất thiết là do trình tối ưu đã cải thiện kế hoạch?

**Đáp án:** không. Kế hoạch giống nhau nhưng dữ liệu có thể đã vào page cache, tài nguyên hệ thống đang ít tải hơn hoặc phát sinh chênh lệch đo đạc. Cần warm-up đồng đều và lặp nhiều lần để kết luận về thời gian.

### Bài 4 — Đánh giá tính đúng đắn

Truy vấn trước dùng `MATCH` mở hai nhánh quan hệ rồi `sum(amount)`; truy vấn sau dùng subquery tổng hợp từng nhánh. Cả hai đều trả một hàng/khách hàng, nhưng tổng tiền khác nhau. Có nên lấy độ trễ của hai truy vấn để báo cáo “tối ưu hiệu năng” không?

**Đáp án:** chưa. Phải kiểm tra phép tổng hợp nào đúng theo nghiệp vụ và đưa các truy vấn về cùng kết quả trước khi so sánh như hai phương án tương đương. Nếu thay đổi sửa cả lỗi kết quả, cần ghi rõ đây là **sửa logic** kèm thay đổi kế hoạch, không chỉ tối ưu tốc độ.

## 14. Ghi nhớ

- **Cùng bộ dữ liệu, cùng tham số, cùng mục tiêu kết quả** là điều kiện đầu tiên của so sánh kế hoạch công bằng.
- **`EXPLAIN` cho biết phương án dự kiến; `PROFILE` cho biết số liệu thực thi.** Cả hai đều cần được đọc theo đúng phiên bản Neo4j đang chạy.
- **Chỉ thay đổi một yếu tố có chủ đích mỗi lần thử.** Khi thử index, giữ nguyên Cypher; khi thử viết lại Cypher, giữ nguyên schema và dữ liệu.
- **Theo dõi `Rows`, `DB Hits`, `Sort`/`Top` và số lượng hàng đầu ra**, kết hợp đo độ trễ nhiều lượt với warm-up tương đương.
- **Chứng minh tính đúng đắn trước khi kết luận tối ưu.** Kế hoạch nhanh hơn nhưng trả sai hoặc thiếu dữ liệu không phải cải thiện hợp lệ.
