# Thiết kế ví dụ tối thiểu để chứng minh một bất biến được giữ

Khi thiết kế NoSQL, việc chọn mô hình dữ liệu không chỉ nhằm làm truy vấn nhanh. Ta còn phải đảm bảo rằng **sau mọi thao tác được phép, dữ liệu không rơi vào một trạng thái mà nghiệp vụ cấm**. Những điều kiện phải luôn đúng như vậy gọi là **bất biến** (*invariant*).

Ví dụ: một cửa hàng chỉ có 5 đơn vị hàng trong kho, nhưng hai khách hàng cùng lúc yêu cầu giữ 4 và 3 đơn vị. Nếu cả hai yêu cầu đều được chấp nhận, hệ thống đã cấp phát tổng cộng 7 đơn vị từ kho chỉ có 5. Lỗi không nhất thiết xuất hiện dưới dạng một con số tồn kho âm: nếu hai request đọc cùng giá trị rồi cùng ghi đè, số tồn lưu trong DBMS còn có thể trông hợp lệ nhưng **không phản ánh những lần cấp phát đã được chấp nhận**.

Bài học này xây dựng **một ví dụ tối thiểu, đủ để lập luận rằng một bất biến cụ thể được giữ**. Ta chọn bài toán cấp phát số lượng hàng từ một kho cho một sản phẩm, lưu trạng thái cần bảo vệ **trong một document MongoDB**, rồi chỉ cập nhật bằng **một thao tác có điều kiện và nguyên tử**. Sau đó ta phân tích truy cập đồng thời, viết kiểm thử nhỏ và xác định chính xác những điều đã — và chưa — được chứng minh.

Điểm quan trọng không phải học thuộc MongoDB. Phương pháp có thể áp dụng rộng hơn:

1. Phát biểu **bất biến** bằng điều kiện có thể kiểm tra.
2. Xác định **nhóm dữ liệu** phải thay đổi cùng nhau.
3. Xác định **trạng thái ban đầu hợp lệ** và **những phép chuyển trạng thái hợp lệ**.
4. Chọn **ranh giới nguyên tử** của DBMS bao trùm nhóm dữ liệu đó.
5. Lập luận rằng từng phép chuyển **không phá bất biến**, kể cả khi có cạnh tranh.
6. Dùng kiểm thử và quan sát để hỗ trợ, nhưng không nhầm một lần kiểm thử thành chứng minh cho mọi tình huống.

## 1. Bất biến là gì?

**Bất biến dữ liệu** là một mệnh đề phải đúng ở những trạng thái mà hệ thống cam kết coi là hợp lệ. Ví dụ:

| Ngữ cảnh | Bất biến minh họa |
| --- | --- |
| Kho hàng | Không cấp phát nhiều hơn lượng sẵn có |
| Hệ thống đặt chỗ | Tổng ghế đã cấp không vượt sức chứa |
| Ví điện tử | Số dư khả dụng không âm, trừ khi sản phẩm cho phép thấu chi |
| Thành viên câu lạc bộ | Một người không có hai tư cách thành viên đang hoạt động cùng loại trong cùng phạm vi |
| Thứ tự trạng thái đơn hàng | Đơn đã hủy không được chuyển trực tiếp sang đã giao nếu quy trình cấm |
| Giỏ hàng | Số lượng mỗi dòng hàng phải là số nguyên dương theo quy tắc nghiệp vụ |
| Báo cáo | Tổng số phần tử theo nhóm phải khớp tập dữ liệu nguồn tại cùng một mốc đối soát |

Những ví dụ này có **phạm vi bảo đảm** khác nhau. Một bất biến có thể chỉ liên quan đến một document; một bất biến khác cần nhiều document, nhiều partition hoặc thậm chí nhiều dịch vụ. Khả năng kiểm soát chúng phụ thuộc mô hình dữ liệu và bảo đảm transaction của DBMS.

### Bất biến khác validation đầu vào thế nào?

Validation đầu vào trả lời câu hỏi: **request này có hợp lệ không?** Bất biến trả lời: **trạng thái dữ liệu sau các request có còn hợp lệ không?**

Ví dụ với yêu cầu giữ hàng:

- Kiểm tra `quantity > 0` và là số nguyên là **validation đầu vào**.
- Bảo đảm `available >= 0` sau mọi lần cấp phát là **bất biến trạng thái**.
- Bảo đảm `available + reservedTotal = capacity` là một **bất biến bảo toàn số lượng** trong mô hình tối thiểu.

Validation tốt vẫn chưa đủ nếu hai request hợp lệ **đồng thời** tác động lên cùng trạng thái nhưng không được phối hợp nguyên tử.

### Bất biến khác quy tắc kết quả của một request

Một request giữ 4 đơn vị có thể hợp lệ nhưng **không được chấp nhận** khi kho chỉ còn 3. Đây không phải lỗi dữ liệu: hệ thống từ chối yêu cầu để bảo vệ bất biến. Khi xây dựng API, nên phân biệt:

- **Request không hợp lệ:** `quantity = -3`, thiếu mã sản phẩm, sai kiểu dữ liệu.
- **Request hợp lệ nhưng không đủ điều kiện hiện tại:** kho chỉ còn 2, khách muốn giữ 4.
- **Request được chấp nhận và đã commit:** thao tác giảm tồn và ghi nhận số lượng cấp phát.
- **Kết quả không xác định từ góc nhìn client:** timeout hoặc mất kết nối, có thể DBMS đã commit nhưng client chưa nhận được phản hồi.

Nhóm cuối rất quan trọng: **bất biến vẫn có thể được giữ trong DBMS dù client không biết chắc thao tác vừa thành công hay thất bại**. Nhưng việc gửi lại request có thể phát sinh một bất biến khác về xử lý trùng.

## 2. Chọn một bài toán tối thiểu có thể chứng minh

Ta chọn một kho và một SKU, không có hoàn trả, hủy giữ hàng, nhập thêm hay điều chỉnh tồn trong phạm vi ví dụ ban đầu.

**Yêu cầu nghiệp vụ:**

> Kho `WH-1` đang có đúng 5 đơn vị sản phẩm `SKU-100`. Một request có thể xin cấp phát `q` đơn vị, trong đó `q` là số nguyên dương. Request chỉ được chấp nhận nếu số lượng còn lại đủ. Mọi request khác nhau có thể đến đồng thời. Hệ thống không được cấp phát vượt quá 5 đơn vị.

Ta lưu ba giá trị:

- `capacity`: tổng số đơn vị đầu kỳ, không đổi trong ví dụ này.
- `available`: số đơn vị chưa cấp phát.
- `reservedTotal`: tổng số đơn vị đã được cấp phát thành công.

Trạng thái ban đầu:

~~~json
{
  "_id": "WH-1:SKU-100",
  "warehouseId": "WH-1",
  "sku": "SKU-100",
  "capacity": 5,
  "available": 5,
  "reservedTotal": 0
}
~~~

**Bất biến cần giữ** với mọi trạng thái đã commit:

\[
\begin{aligned}
I_1 &: \quad available \ge 0 \\
I_2 &: \quad reservedTotal \ge 0 \\
I_3 &: \quad available + reservedTotal = capacity
\end{aligned}
\]

Vì `capacity = 5` và cả `available`, `reservedTotal` không âm, suy ra `reservedTotal <= 5`. Đây chính là phát biểu “không cấp phát vượt quá 5 đơn vị” bằng điều kiện kiểm tra trực tiếp trên dữ liệu.

### Vì sao dùng cả available và reservedTotal?

Nếu chỉ lưu `available`, ta vẫn có thể ngăn số đó âm bằng cập nhật có điều kiện. Nhưng việc lưu thêm `reservedTotal` trong **cùng một đơn vị cập nhật nguyên tử** cho phép quan sát một bất biến mạnh hơn: tổng số hàng còn và hàng đã cấp phải đúng bằng `capacity`.

Mô hình này cố ý tối giản:

- Chưa ghi **đơn hàng nào sở hữu phần cấp phát**.
- Chưa hỗ trợ **giữ hàng hết hạn** hoặc **trả hàng**.
- Chưa có thanh toán.
- Chưa có chuyển hàng giữa kho.
- Chưa ghi lịch sử từng request.

Những yêu cầu trên có thể quan trọng trong hệ thống thật, nhưng thêm tất cả cùng lúc sẽ làm mờ bài học **chứng minh một invariant được bảo vệ bằng ranh giới nguyên tử**.

## 3. Xác định nhóm dữ liệu phải nhất quán

Với ba giá trị `capacity`, `available`, `reservedTotal`, điều kiện `available + reservedTotal = capacity` liên quan đồng thời đến nhiều trường. Nếu một thao tác giảm `available` nhưng chưa tăng `reservedTotal`, trạng thái ở giữa sẽ phá `I_3`.

Giả sử cập nhật bằng hai lệnh độc lập:

~~~text
Lệnh A: available = available - 3
Lệnh B: reservedTotal = reservedTotal + 3
~~~

Nếu lệnh A thành công còn B thất bại, ta có thể nhận:

~~~text
capacity      = 5
available     = 2
reservedTotal = 0

available + reservedTotal = 2 != 5
~~~

Vậy trong ví dụ này, hai trường cần cùng thay đổi phải nằm **trong một ranh giới cập nhật nguyên tử**.

Ta chọn một document:

~~~text
inventory:

_id = "WH-1:SKU-100"
  ├── capacity = 5
  ├── available = 5
  └── reservedTotal = 0

Một phép cấp phát:
  kiểm tra available >= q
            │
            ▼
  giảm available và tăng reservedTotal
            │
            ▼
  commit như một lần cập nhật document
~~~

Trong MongoDB, **một thao tác ghi trên một document có tính nguyên tử ở phạm vi document đó**. Vì thế, ta có thể cập nhật hai trường cùng nhau bằng một lệnh `updateOne`. Đây là lý do chọn document làm **nhóm dữ liệu nhất quán** (*consistency boundary*) cho ví dụ.

**Chọn “cùng document” không phải công thức luôn đúng.** Nếu document phình quá lớn, nếu nhiều đối tượng cần sửa cùng nhau, hoặc nếu throughput của một khóa quá cao, ta còn phải đánh giá các đánh đổi khác. Nhưng với ba bộ đếm nhỏ, một SKU trong một kho, ranh giới này hợp lý để minh họa.

## 4. Phép chuyển trạng thái được phép

Một request cấp phát `q` được chấp nhận khi:

\[
q \in \mathbb{Z}, \qquad q > 0, \qquad available \ge q
\]

Nếu được chấp nhận, trạng thái chuyển:

\[
\begin{aligned}
available' &= available - q \\
reservedTotal' &= reservedTotal + q \\
capacity' &= capacity
\end{aligned}
\]

Nếu `available < q`, thao tác **không thay đổi trạng thái**.

Ví dụ:

| Trạng thái trước | Yêu cầu | Kết quả | Trạng thái sau |
| --- | --- | --- | --- |
| `(available=5, reserved=0)` | Cấp 2 | Thành công | `(3,2)` |
| `(available=3, reserved=2)` | Cấp 3 | Thành công | `(0,5)` |
| `(available=0, reserved=5)` | Cấp 1 | Từ chối | `(0,5)` |
| `(available=3, reserved=2)` | Cấp 4 | Từ chối | `(3,2)` |

Ở mỗi trạng thái thành công, tổng `available + reservedTotal` vẫn bằng 5; không xuất hiện `available < 0`.

### Quy tắc “mọi thao tác đều phải đi qua cổng này”

Chứng minh chỉ đúng nếu **mọi thao tác được phép làm thay đổi ba trường** đều bảo toàn điều kiện.

Ví dụ, một script quản trị có quyền thực hiện:

~~~javascript
db.inventory.updateOne(
  { _id: "WH-1:SKU-100" },
  { $set: { available: -100 } }
);
~~~

Lệnh đó sẽ phá `I_1` nếu không bị validation/quyền truy cập/chính sách ghi ngăn lại. Không thể nói “dữ liệu luôn hợp lệ” chỉ vì đường checkout dùng một truy vấn đúng, trong khi đường admin hoặc migration được phép ghi tùy ý.

**Phạm vi chứng minh** phải bao gồm những đường ghi được cho phép trong hệ thống hoặc nói rõ những đường ghi nào đang nằm ngoài ví dụ.

## 5. Cách viết sai: đọc rồi mới quyết định và ghi

Một triển khai dễ gặp:

~~~javascript
// Ví dụ SAI khi có nhiều client ghi đồng thời.
const current = await inventory.findOne({
  _id: "WH-1:SKU-100"
});

if (current.available >= quantity) {
  await inventory.updateOne(
    { _id: "WH-1:SKU-100" },
    {
      $set: {
        available: current.available - quantity,
        reservedTotal: current.reservedTotal + quantity
      }
    }
  );

  return true;
}

return false;
~~~

Từng lệnh đọc và ghi có thể hợp lệ, nhưng **điều kiện kiểm tra và thao tác ghi không phải một quyết định nguyên tử**. Hai client có thể cùng đọc một trạng thái cũ.

### Lịch thực thi gây mất cập nhật

Tồn ban đầu: `available=5`, `reservedTotal=0`.

| Thời điểm | Client A muốn 4 | Client B muốn 3 | Document lưu |
| --- | --- | --- | --- |
| T0 | — | — | `available=5, reservedTotal=0` |
| T1 | Đọc `available=5` | — | Chưa đổi |
| T2 | — | Đọc `available=5` | Chưa đổi |
| T3 | Điều kiện `5>=4` đúng | — | Chưa đổi |
| T4 | — | Điều kiện `5>=3` đúng | Chưa đổi |
| T5 | Ghi `(1,4)` và báo thành công | — | `(1,4)` |
| T6 | — | Ghi `(2,3)` và báo thành công | `(2,3)` |

Cuối cùng document vẫn có `available + reservedTotal = 5`, nhưng **hai client đều đã nhận “thành công”** với tổng yêu cầu 7 đơn vị. Trạng thái lưu chỉ ghi nhận một phần cấp phát; nghiệp vụ đã chấp nhận quá số hàng ban đầu.

Điều này cho thấy:

1. Không nên chỉ kiểm tra bất biến trên **trạng thái cuối** khi hệ thống còn có các **cam kết đã trả cho client**.
2. Muốn chứng minh điều kiện không oversell, phải nối được **quyết định chấp nhận** với một **chuyển trạng thái đã commit**.
3. Lấy `available` ra ngoài ứng dụng để kiểm tra rồi ghi đè có thể tạo cuộc đua giữa **đọc–kiểm tra–ghi** (*check-then-act race*).

Một biến thể sai khác là chỉ dùng `$inc: {available: -q}` mà **không có điều kiện `available >= q`**. Cách đó tránh lost update vì tăng/giảm là atomic, nhưng có thể làm `available` âm khi lượng yêu cầu vượt tồn kho. Để giữ bất biến, phải có **cả điều kiện và cập nhật nguyên tử**.

## 6. Cách viết đúng: điều kiện và thay đổi trong một lệnh

Với MongoDB, thao tác cấp phát có thể là:

~~~javascript
const result = await inventory.updateOne(
  {
    _id: "WH-1:SKU-100",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reservedTotal: quantity
    }
  }
);

const accepted = result.matchedCount === 1;
~~~

Giải thích:

- Bộ lọc `_id` định vị **đúng document** của SKU và kho.
- Điều kiện `available: {$gte: quantity}` chỉ khớp khi còn đủ đơn vị.
- Hai phép tăng/giảm trong `$inc` là **một thao tác cập nhật trên document**.
- `matchedCount = 1` cho biết một document phù hợp điều kiện và được chọn để cập nhật. Với `quantity` dương và các trường hợp lệ, thao tác sẽ thay đổi số lượng; nếu không khớp, không có cấp phát.
- Không dùng `upsert: true`: nếu document không tồn tại, thao tác phải bị từ chối, không tạo ngẫu nhiên một document thiếu các trường bất biến.

**Cần validate đầu vào trước lệnh**:

~~~javascript
function requirePositiveQuantity(quantity) {
  if (!Number.isSafeInteger(quantity) || quantity <= 0) {
    throw new Error("quantity must be a positive safe integer");
  }
}
~~~

Nếu cho phép `quantity = -3`, bộ lọc `available >= -3` có thể khớp và `$inc` làm **tăng available, giảm reservedTotal**, phá mô hình nghiệp vụ. Nếu cho phép số thập phân hoặc kiểu string mà không kiểm soát, điều kiện và phép số học có thể không còn mang đúng nghĩa “số đơn vị hàng”.

Trong hệ thống thực tế, còn phải thống nhất các kiểu số, giới hạn cực đại, xử lý overflow, số lượng hàng có thể âm theo nghiệp vụ hay không, và quyền gọi thao tác cấp phát.

### Ví dụ khi hai client cạnh tranh

Ban đầu `available=5`. A xin 4 và B xin 3, có thể xảy ra:

~~~text
Trường hợp A được xử lý trước:

A: điều kiện 5 >= 4 đúng
   cập nhật thành (available=1, reservedTotal=4)

B: điều kiện 1 >= 3 sai
   không cập nhật

Kết quả: A thành công, B bị từ chối
~~~

Hoặc B được xử lý trước:

~~~text
B: điều kiện 5 >= 3 đúng
   cập nhật thành (available=2, reservedTotal=3)

A: điều kiện 2 >= 4 sai
   không cập nhật

Kết quả: B thành công, A bị từ chối
~~~

Ta **không cần dự đoán request nào thắng**. Điều cần bảo đảm là hai request không thể cùng chấp nhận nếu tổng số lượng vượt khả năng cấp phát. Điều kiện được kiểm tra như một phần của phép ghi nguyên tử trên cùng document; không dùng một snapshot `available=5` đã đọc trước để ra quyết định tại client.

## 7. Chứng minh bất biến bằng quy nạp trên các lần cập nhật

Một kiểm thử có thể tìm lỗi, nhưng để giải thích **vì sao invariant được giữ**, ta cần chỉ ra rằng:

- Trạng thái đầu thỏa invariant.
- Mọi phép chuyển được phép nếu xuất phát từ trạng thái hợp lệ đều dẫn tới trạng thái hợp lệ.

Đây là một lập luận quy nạp đơn giản.

### Bước cơ sở: trạng thái ban đầu

Với:

~~~text
capacity      = 5
available     = 5
reservedTotal = 0
~~~

Ta có:

\[
5\ge 0,\quad 0\ge 0,\quad 5+0=5
\]

Vậy `I_1`, `I_2`, `I_3` đều đúng.

### Bước quy nạp: một yêu cầu tiếp theo

Giả sử trước khi xử lý yêu cầu, trạng thái thỏa:

\[
available\ge0,\quad reservedTotal\ge0,\quad
available+reservedTotal=capacity
\]

Xét yêu cầu `q` là số nguyên dương.

**Trường hợp 1 — điều kiện không khớp:** `available < q`. DBMS không thay đổi document nên toàn bộ invariant vẫn đúng.

**Trường hợp 2 — điều kiện khớp:** `available >= q`. Sau cập nhật:

\[
available'=available-q\ge0
\]

\[
reservedTotal'=reservedTotal+q\ge0
\]

Và:

\[
\begin{aligned}
available'+reservedTotal'
&=(available-q)+(reservedTotal+q)\\
&=available+reservedTotal\\
&=capacity
\end{aligned}
\]

Do đó, invariant vẫn đúng sau phép cập nhật.

**Kết luận:** nếu trạng thái ban đầu hợp lệ và **chỉ có những phép chuyển đã mô tả**, thì sau bất kỳ số lần cập nhật thành công hay bị từ chối, các invariant vẫn được giữ.

### Đâu là vai trò của atomicity?

Lập luận trên giả định mỗi lần chuyển trạng thái là **một bước logic nguyên tử**: kiểm tra `available >= q` và cập nhật hai bộ đếm tạo thành **một quyết định không bị chen một phép ghi khác vào giữa** trên cùng document.

Với nhiều client, MongoDB sẽ xử lý các cập nhật trên cùng document sao cho điều kiện cập nhật có hiệu lực tại thời điểm thao tác ghi, thay vì tin vào một điều kiện đã kiểm tra từ trước ở client. Có thể hình dung các cập nhật thành công đã được sắp thành một thứ tự logic. Ta áp dụng bước quy nạp cho từng cập nhật theo thứ tự đó.

Không cần toàn bộ hệ thống xử lý request tuần tự trên một thread. Điều cần có là **phạm vi nguyên tử của thao tác đã bao trùm những trường cấu thành invariant**.

### Bất biến nào đã được chứng minh?

Trong giới hạn của ví dụ:

\[
0\le reservedTotal\le capacity,\qquad
available=capacity-reservedTotal
\]

Do đó **số đơn vị được các cập nhật đã commit ghi nhận là đã cấp phát** không vượt quá khả năng ban đầu.

Để gắn tuyên bố đó với kết quả nghiệp vụ, ứng dụng phải **chỉ báo “được cấp phát” sau khi thao tác tương ứng đã commit thành công** và có chính sách xử lý lỗi/timeout phù hợp. Không thể cho hai client tự báo thành công từ điều kiện đọc cũ rồi viện dẫn trạng thái DB cuối để khẳng định không oversell.

## 8. Thực hành tối thiểu với MongoDB

Ta có thể dùng một môi trường MongoDB thử nghiệm và MongoDB Node.js Driver để quan sát tình huống hai lời gọi cạnh tranh.

**Điều kiện thực hiện:**

- MongoDB đã chạy tại một địa chỉ mà bạn có quyền sử dụng để thử nghiệm.
- Máy có Node.js và package `mongodb` phù hợp.
- Chỉ thao tác với database thử nghiệm, không dùng dữ liệu đơn hàng hoặc tồn kho thật.

Trong một project Node.js, có thể cài thư viện:

~~~bash
npm install mongodb
~~~

Lưu mã sau vào file ví dụ `inventory-invariant-demo.mjs`. Đây là nội dung minh họa của bài học; STEP 4 chỉ biên soạn Markdown, **không chạy test hay tạo file mã ngoài Markdown**.

~~~javascript
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { MongoClient } from "mongodb";

const client = new MongoClient(
  process.env.MONGODB_URI ?? "mongodb://127.0.0.1:27017"
);

const collection = client
  .db("nosql_invariant_training")
  .collection("inventory_example");

// ID riêng để không đụng tới bản ghi của lần chạy khác.
const inventoryId = "proof-" + randomUUID();
let inserted = false;

function assertQuantity(q) {
  if (!Number.isSafeInteger(q) || q <= 0) {
    throw new Error("quantity must be a positive safe integer");
  }
}

async function reserve(q) {
  assertQuantity(q);

  const result = await collection.updateOne(
    {
      _id: inventoryId,
      available: { $gte: q }
    },
    {
      $inc: {
        available: -q,
        reservedTotal: q
      }
    }
  );

  return result.matchedCount === 1;
}

async function readState() {
  return collection.findOne({ _id: inventoryId });
}

function assertInvariant(state) {
  assert.equal(state.capacity, 5);
  assert.ok(state.available >= 0);
  assert.ok(state.reservedTotal >= 0);
  assert.equal(
    state.available + state.reservedTotal,
    state.capacity
  );
}

try {
  await client.connect();

  await collection.insertOne({
    _id: inventoryId,
    warehouseId: "WH-1",
    sku: "SKU-100",
    capacity: 5,
    available: 5,
    reservedTotal: 0
  });
  inserted = true;

  const initial = await readState();
  assertInvariant(initial);

  // Hai yêu cầu được gửi mà không đợi nhau hoàn tất.
  const [accepted4, accepted3] = await Promise.all([
    reserve(4),
    reserve(3)
  ]);

  const after = await readState();
  assertInvariant(after);

  // Tổng số yêu cầu 4 + 3 > 5: chỉ một yêu cầu được chấp nhận.
  assert.equal(Number(accepted4) + Number(accepted3), 1);

  const expectedReserved = accepted4 ? 4 : 3;
  assert.equal(after.reservedTotal, expectedReserved);
  assert.equal(after.available, 5 - expectedReserved);

  // Yêu cầu quá lớn phải bị từ chối và không đổi trạng thái.
  assert.equal(await reserve(6), false);
  const afterRejected = await readState();
  assertInvariant(afterRejected);
  assert.equal(afterRejected.available, after.available);
  assert.equal(afterRejected.reservedTotal, after.reservedTotal);

  // Đầu vào không hợp lệ phải bị chặn trước khi gọi DBMS.
  await assert.rejects(reserve(0));
  await assert.rejects(reserve(-1));
  await assert.rejects(reserve(1.5));

  console.log({
    accepted4,
    accepted3,
    available: after.available,
    reservedTotal: after.reservedTotal,
    invariantHeld: true
  });
} finally {
  try {
    if (inserted) {
      await collection.deleteOne({ _id: inventoryId });
    }
  } finally {
    await client.close();
  }
}
~~~

### Kết quả hợp lệ có thể nhận được

Tùy yêu cầu nào được xử lý trước, một trong hai kết quả sau có thể xuất hiện:

~~~json
{
  "accepted4": true,
  "accepted3": false,
  "available": 1,
  "reservedTotal": 4,
  "invariantHeld": true
}
~~~

Hoặc:

~~~json
{
  "accepted4": false,
  "accepted3": true,
  "available": 2,
  "reservedTotal": 3,
  "invariantHeld": true
}
~~~

**Không được yêu cầu A luôn thắng B.** Thứ tự request được xử lý có thể thay đổi. Điều được kiểm tra là **không thể cả hai cùng thành công** trong tình huống tổng yêu cầu vượt khả năng.

### Tại sao kiểm thử có ích nhưng chưa phải chứng minh hình thức?

`Promise.all` gửi hai thao tác mà không đợi từng thao tác hoàn tất; đó là một bài thử hữu ích về cạnh tranh. Tuy nhiên:

- Không phải mọi lần chạy đều tạo cùng một lịch xen kẽ ở server.
- Một lần chạy không bao quát hàng triệu lịch thực thi có thể có.
- Kiểm thử thành công không chứng minh rằng những script khác trong hệ thống không ghi sai.
- Kiểm thử không mô phỏng đầy đủ network partition, failover, driver retry, nạp dữ liệu lịch sử hay thao tác quản trị.

Sự bảo đảm chính đến từ **đặc tả phép chuyển + điều kiện cập nhật + tính nguyên tử trên một document**. Kiểm thử giúp phát hiện lỗi triển khai, sai kiểu dữ liệu, sai tên trường hoặc nhầm cách đọc kết quả lệnh.

## 9. Lập bảng trường hợp thay vì chỉ thử “happy path”

Một ví dụ tối thiểu có chất lượng cần gồm **trường hợp thành công, thất bại, ranh giới và cạnh tranh**.

| Trường hợp | Trạng thái đầu | Request | Kỳ vọng |
| --- | --- | --- | --- |
| Cấp phát bình thường | `available=5` | `q=2` | Chấp nhận; `available=3`, `reservedTotal=2` |
| Cấp hết số còn | `available=5` | `q=5` | Chấp nhận; `available=0` |
| Vượt số còn | `available=2` | `q=3` | Từ chối; không đổi |
| Kho hết | `available=0` | `q=1` | Từ chối; không âm |
| Số lượng bằng 0 | Bất kỳ hợp lệ | `q=0` | Lỗi validation, không gọi DBMS |
| Số lượng âm | Bất kỳ hợp lệ | `q=-1` | Lỗi validation |
| Số thập phân | Bất kỳ hợp lệ | `q=1.5` | Lỗi validation |
| Hai request vượt tổng | `available=5` | `q=4` và `q=3` đồng thời | Đúng một thành công |
| Hai request vừa tổng | `available=5` | `q=2` và `q=3` đồng thời | Cả hai có thể thành công, còn 0 |
| Document không tồn tại | Không có bản ghi | `q=1` | Không upsert; từ chối hoặc báo không tồn tại |
| Document dữ liệu sai kiểu | `available="5"` | `q=2` | Phải phát hiện dữ liệu lỗi, không coi là kho hợp lệ |

Điều kiện `$gte` là một phần của giải pháp nhưng **không thay thế validation dữ liệu ban đầu**. Nếu có script nhập dữ liệu để `reservedTotal` âm hoặc tạo document thiếu `capacity`, bước quy nạp ban đầu không còn đúng.

### Kiểm thử với nhiều request đồng thời

Một bài thử căng thẳng bổ sung có thể:

1. Tạo document với `capacity=1000`, `available=1000`, `reservedTotal=0`.
2. Gửi 2.000 yêu cầu, mỗi yêu cầu xin 1 đơn vị.
3. Đợi tất cả thao tác có kết quả hoặc ghi nhận những thao tác chưa rõ trạng thái.
4. Kiểm tra invariant cuối và số lượng cập nhật được DBMS ghi nhận.
5. Lặp lại với số lượng yêu cầu khác nhau, retry và tải cao.

Nếu tất cả lệnh hoàn thành bình thường, số request được chấp nhận phải đúng 1.000; tuy nhiên, khi có timeout không rõ commit, **không thể suy từ số phản hồi thành công để đếm chính xác số lần đã ghi vào DBMS**. Trường hợp này dẫn tới yêu cầu về idempotency và trạng thái theo request.

## 10. Phạm vi nguyên tử: khi nào gom dữ liệu vào một document?

Nguyên tắc thiết kế:

> Nếu nhiều thuộc tính phải thay đổi cùng nhau để giữ một bất biến, hãy cân nhắc đặt chúng **trong cùng đơn vị cập nhật nguyên tử**, miễn là cách đó còn đáp ứng kích thước, tốc độ và các mẫu truy cập thực tế.

Ví dụ:

| Bất biến | Nhóm dữ liệu cần xét | Ranh giới có thể khảo sát |
| --- | --- | --- |
| Một SKU không cấp phát vượt tồn của một kho | `available`, `reservedTotal`, `capacity` của SKU–kho | Một document |
| Một giỏ hàng không có dòng hàng số lượng âm | Các dòng hàng, quy tắc cập nhật giỏ | Một document hoặc cấu trúc có phép cập nhật nguyên tử |
| Một tài khoản không có số dư âm | Số dư và thao tác trừ có điều kiện | Một bản ghi tài khoản nếu quy tắc chỉ phụ thuộc tài khoản đó |
| Một lần đăng ký có trạng thái chuyển hợp lệ | Trạng thái và revision của lần đăng ký | Một record/document với compare-and-set |
| Chuyển tiền giữa hai tài khoản phải bảo toàn tổng | Ít nhất hai tài khoản và bản ghi giao dịch liên quan | Transaction nhiều record hoặc giao thức nghiệp vụ phù hợp |
| Đơn hàng chốt phải có đúng tập dòng hàng | Đơn, dòng hàng và snapshot giá | Có thể nhúng chung, hoặc dùng transaction theo yêu cầu |

### Gom theo invariant, nhưng không gom vô hạn

Giả sử một document kho hàng chứa **toàn bộ sản phẩm của kho** để mọi phép thay đổi số lượng đều nguyên tử trong một document:

~~~text
warehouse:WH-1
  products:
    SKU-1: ...
    SKU-2: ...
    SKU-3: ...
    ...
    SKU-1.000.000: ...
~~~

Đây không phải mô hình tốt chỉ vì “mọi thứ cùng một document”. Tài liệu có thể vượt giới hạn kích thước của DBMS, tạo hot document, cạnh tranh ghi và làm truy vấn đơn SKU tốn kém.

Ta nên chọn **ranh giới nhỏ nhất đủ để bảo vệ invariant**. Nếu bất biến là số hàng của **một SKU tại một kho**, document theo khóa `(warehouseId, sku)` có thể đủ. Không phải mọi SKU trong kho đều phải cập nhật nguyên tử cùng nhau.

### Tìm bất biến thật sự trước khi chọn aggregate

Hãy thử câu hỏi:

- Khi cập nhật thông tin này, những giá trị nào **phải cùng đổi** để không tạo trạng thái bị cấm?
- Những đối tượng nào có thể thay đổi độc lập?
- Có thao tác nào phải nhìn thấy trạng thái trung gian không?
- Một tài liệu có bị sửa rất thường xuyên từ nhiều client không?
- Có ràng buộc ngoài document, như thanh toán, số dư tổng, quyền giữ hàng theo đơn hay giới hạn toàn hệ thống không?

Nhóm dữ liệu có thể được gọi là **aggregate** trong thiết kế miền; tuy vậy, ranh giới aggregate nghiệp vụ và **ranh giới nguyên tử thực sự của DBMS** phải được đối chiếu, không tự mặc định chúng luôn trùng.

## 11. Khi invariant nằm trên nhiều document

Ví dụ thực tế thường có ít nhất:

~~~text
inventory:
  WH-1:SKU-100 → available=2, reservedTotal=3

orders:
  O-1001 → status=PENDING, items=[SKU-100 × 3]
~~~

Giả sử yêu cầu:

> “Nếu đã ghi một đơn hàng ở trạng thái `RESERVED` thì đúng số hàng tương ứng phải được giữ, và không được có hàng đã giữ mà không có một đơn yêu cầu hợp lệ.”

Invariant này liên quan **hai document**: tồn kho và đơn hàng. Lệnh `updateOne` trên inventory có thể giữ số lượng không âm, nhưng **không tự bảo đảm** đơn hàng được tạo hoặc đổi trạng thái thành công.

### Lỗi khi cập nhật tuần tự hai document

~~~text
1. Giảm available, tăng reservedTotal trong inventory → thành công.
2. Tạo order hoặc đổi trạng thái order → lỗi mạng/DB.

Kết quả:
  Inventory đã giữ hàng.
  Order chưa phản ánh phần giữ hàng.
~~~

Đảo thứ tự cũng không tự giải quyết:

~~~text
1. Ghi order RESERVED → thành công.
2. Cập nhật inventory → không đủ hàng hoặc lỗi.

Kết quả:
  Order nói đã giữ hàng.
  Inventory chưa giữ tương ứng.
~~~

Đây là lý do phải nêu rõ **invariant cần chứng minh**. Ví dụ tối thiểu ở phần đầu chứng minh số lượng **không vượt sức chứa trong inventory document**; nó **chưa chứng minh** tính nhất quán tức thời giữa inventory và orders.

### Những hướng thiết kế khi bất biến vượt document

**Hướng 1 — Gom nhóm dữ liệu phù hợp nếu nhỏ và cùng vòng đời.** Nếu các thông tin luôn được đọc/ghi cùng nhau và giới hạn kích thước cho phép, có thể nhúng trong một document. Nhưng nếu một SKU có hàng triệu đơn, lưu mọi reservation vào một document có thể không khả thi.

**Hướng 2 — Transaction nhiều document.** Một số DBMS như MongoDB hỗ trợ transaction nhiều document với những điều kiện và đánh đổi cụ thể. Có thể cập nhật tồn và ghi order trong một transaction, nhưng phải quản lý transaction lifetime, conflict/retry, write concern và khả năng hạ tầng. Không được suy luận mọi NoSQL DBMS đều có khả năng này hoặc có cùng chi phí.

**Hướng 3 — Quy trình trạng thái và bù trừ (*saga/compensation*).** Nếu các bước nằm trên nhiều dịch vụ, có thể đặt trạng thái `PENDING` rồi xác nhận `RESERVED` sau khi inventory thực sự chấp nhận, hoặc bù trừ khi bước sau thất bại. Cách này thường cho phép **trạng thái trung gian**; không thể tuyên bố có invariant tức thời mạnh trên mọi dịch vụ trừ khi giao thức thực sự bảo đảm nó.

**Hướng 4 — Tách invariant thành những điều kiện cục bộ và điều kiện hội tụ.** Chẳng hạn inventory không âm được bảo đảm ngay tại nguồn; việc order phản ánh inventory có thể đạt nhất quán cuối cùng với retry, đối soát và trạng thái hiển thị rõ ràng. Đây là lựa chọn nghiệp vụ, không phải cách “bỏ qua” điều kiện an toàn.

### Một ví dụ phân cấp invariant

| Phát biểu | Phạm vi | Ví dụ đầu bài đã đủ chứng minh? |
| --- | --- | --- |
| `available >= 0` | Một document inventory | **Có**, theo những giả định đã nêu |
| `available + reservedTotal = capacity` | Một document inventory | **Có**, theo những giả định đã nêu |
| Một request ID chỉ được cấp phát tối đa một lần | Inventory **và danh tính request** | **Chưa** |
| Mỗi đơn trạng thái RESERVED có một reservation tương ứng | Inventory và order | **Chưa** |
| Thanh toán và giữ hàng luôn hoàn tất cùng nhau | Nhiều dịch vụ/nguồn | **Chưa** |
| Tổng tồn trên mọi kho đúng bằng một con số toàn hệ thống | Nhiều document/kho | **Chưa** |

Biết **mình chưa chứng minh điều gì** cũng là một phần bắt buộc của thiết kế đúng đắn.

## 12. Retry và idempotency: giữ invariant chưa đủ để chống cấp phát trùng

Một tình huống phổ biến:

~~~text
Client gửi: reserve 2 units, requestId = R-101
         │
         ▼
MongoDB commit: available 5 → 3
         │
         X  Phản hồi bị mất do lỗi mạng
         │
         ▼
Client không chắc đã thành công
         │
         ▼
Client retry cùng requestId = R-101
~~~

Nếu client gọi lại hàm `reserve(2)` ban đầu, DBMS có thể **cấp phát thêm 2 lần nữa** khi còn đủ hàng. Trạng thái cuối vẫn có thể thỏa `available >= 0` và `available + reservedTotal = capacity`, nhưng một hành động nghiệp vụ đã dùng 4 đơn vị thay vì 2.

Đây là **bất biến khác**:

> Với mỗi `requestId` hợp lệ, số lần cấp phát được ghi nhận phải không vượt quá một.

Để bảo vệ điều kiện này, hệ thống cần giữ dấu vết `requestId` và quyết định cấp phát **cùng một ranh giới nhất quán** hoặc qua một giao thức transaction/idempotency phù hợp.

### Một minh họa mở rộng trong một document

Với một tập cấp phát nhỏ và bị giới hạn, có thể lưu các ID đã xử lý trong cùng document:

~~~json
{
  "_id": "WH-1:SKU-100",
  "capacity": 5,
  "available": 5,
  "reservedTotal": 0,
  "acceptedRequestIds": []
}
~~~

Và dùng cập nhật có điều kiện:

~~~javascript
const result = await inventory.updateOne(
  {
    _id: "WH-1:SKU-100",
    available: { $gte: quantity },
    acceptedRequestIds: { $ne: requestId }
  },
  {
    $inc: {
      available: -quantity,
      reservedTotal: quantity
    },
    $addToSet: {
      acceptedRequestIds: requestId
    }
  }
);
~~~

Trong một thao tác nguyên tử, điều kiện kiểm tra cả **số lượng** và **ID chưa được dùng**, đồng thời ghi nhận ID cùng việc trừ tồn. Với nhiều retry cùng ID, chỉ một lần cập nhật có thể khớp trong phạm vi các thao tác đã mô tả.

**Giới hạn của minh họa:**

- Nếu `matchedCount = 0`, nguyên nhân có thể là **không đủ hàng**, **ID đã xử lý** hoặc **document không tồn tại**. Muốn trả kết quả idempotent đúng cho client, phải tra cứu trạng thái của request và xác nhận dữ liệu request (ví dụ quantity) có khớp với lần đã ghi trước.
- Mảng `acceptedRequestIds` tăng theo thời gian, làm document lớn và tăng hot-spot. Nó **không phù hợp** khi một SKU có số lượng request không giới hạn.
- Mỗi ID phải ổn định, không trùng giữa những thao tác nghiệp vụ khác nhau, và có chính sách retention.
- Nếu client tái sử dụng cùng ID với lượng yêu cầu khác, phải trả lỗi xung đột thay vì coi là cùng request.
- Nếu hệ thống cần hủy/giải phóng reservation, phải theo dõi lượng đã giữ **theo từng reservation**, chứ không chỉ một mảng ID.

Với hệ thống thật quy mô lớn, có thể chọn collection reservations riêng có unique constraint theo request ID và transaction phù hợp, hoặc giao thức cấp phát có trạng thái. Ví dụ mảng chỉ giúp thấy **một bất biến bổ sung sẽ đòi hỏi dữ liệu và điều kiện bổ sung như thế nào**.

## 13. Nếu hệ thống cho phép trả hàng, hủy hoặc nhập thêm

Ví dụ tối thiểu giả định `capacity` cố định và chỉ có cấp phát. Khi mở rộng nghiệp vụ, ta phải **định nghĩa lại tập thao tác và chứng minh cho từng thao tác**.

### Hủy giữ hàng

Với yêu cầu trả lại `q` đơn vị từng được giữ:

\[
\begin{aligned}
available' &= available+q\\
reservedTotal' &= reservedTotal-q
\end{aligned}
\]

Muốn giữ `reservedTotal' >= 0`, cần điều kiện `reservedTotal >= q`. Nhưng điều kiện tổng này **chưa đủ** để chứng minh một reservation cụ thể được hủy đúng một lần. Ví dụ hai request hủy cùng một reservation 2 đơn vị có thể đều thành công nếu tổng `reservedTotal` còn lớn hơn 4 do các reservation khác tồn tại.

Vì thế, khi thêm thao tác hủy, nên xem xét **định danh từng reservation**, số lượng gắn với reservation, trạng thái `ACTIVE/RELEASED` và điều kiện chỉ chuyển trạng thái một lần.

### Nhập thêm hàng

Nếu nhập thêm `q` đơn vị hợp lệ:

\[
\begin{aligned}
capacity' &= capacity+q\\
available' &= available+q\\
reservedTotal' &= reservedTotal
\end{aligned}
\]

Phép chuyển này cũng bảo toàn `available+reservedTotal=capacity`, miễn `q > 0` và các phép cộng không vượt giới hạn biểu diễn số.

### Điều chỉnh tồn do kiểm kê

Một lần kiểm kê có thể phát hiện số hàng thực ít hơn dữ liệu. Không thể chỉ sửa `capacity` xuống thấp hơn `reservedTotal` rồi vẫn khẳng định tất cả reservation còn có thể được đáp ứng. Khi đó phải có **quy tắc nghiệp vụ về thiếu hụt hàng**: điều chỉnh hàng chưa cấp phát, đánh dấu thiếu hụt, phân bổ lại hoặc báo sự cố để xử lý.

Kết luận: không được thêm một lệnh ghi “đặc biệt” rồi cho rằng bất biến ban đầu vẫn đúng mà không chứng minh trường hợp mới.

## 14. Bất biến trạng thái và bất biến hành vi

Bài toán trên cho thấy sự khác biệt giữa:

**Bất biến trạng thái**

~~~text
available >= 0
reservedTotal >= 0
available + reservedTotal = capacity
~~~

**Bất biến hành vi**

~~~text
Mỗi requestId không được cấp phát quá một lần.
Không báo thành công nếu chưa có cập nhật commit tương ứng.
Không chuyển một reservation từ RELEASED về ACTIVE tùy ý.
Mọi order RESERVED phải có reservation hợp lệ.
~~~

Bất biến trạng thái có thể kiểm tra bằng một lần đọc document. Bất biến hành vi có thể đòi hỏi **danh tính thao tác, lịch sử, phiên bản, thứ tự sự kiện hoặc liên kết nhiều thực thể**. Một con số cuối cùng trông hợp lệ **không luôn chứng minh hệ thống đã xử lý đúng mọi request**.

### Lịch sử làm rõ những cam kết đã đưa ra

Giả sử hệ thống có log:

~~~text
R-101: reserve 4 → success
R-102: reserve 3 → success
~~~

Khi `capacity=5`, hai phản hồi này đã chứng minh có lỗi nghiệp vụ, kể cả khi document cuối cùng ghi `available=2, reservedTotal=3`. Do đó những hệ có yêu cầu kiểm toán cần thiết kế lịch sử hoặc trạng thái request sao cho một **cam kết với người dùng** có thể đối chiếu với **chuyển trạng thái đã commit**.

Một invariant hữu ích nên chỉ rõ **đối tượng được quan sát**: dữ liệu lưu trong một document, toàn bộ nghiệp vụ phân tán, hay các phản hồi đã trả cho client.

## 15. Chọn cơ chế theo DBMS thay vì suy luận từ nhãn NoSQL

“NoSQL” không phải một bộ bảo đảm nhất quán duy nhất. Để thiết kế ví dụ có thể chứng minh, phải biết **đơn vị atomicity**, **cách áp điều kiện ghi** và **hành vi khi có cạnh tranh** của DBMS cụ thể.

| Loại hệ/cơ chế | Hướng bảo vệ invariant | Điều cần xác minh |
| --- | --- | --- |
| **Document DBMS** như MongoDB | Cập nhật có điều kiện nhiều trường trong một document | Atomicity trên một document, điều kiện match, transaction nếu vượt document |
| **Key–value** như Redis | Lệnh nguyên tử hoặc script thực hiện kiểm tra và cập nhật cùng nhau | Kiểu dữ liệu, phạm vi một/nhiều key, cluster và retry |
| **Wide-column** như Cassandra | Thiết kế key/partition và điều kiện ghi theo khả năng DBMS, có thể cần LWT | Phạm vi compare-and-set, tải/độ trễ, partition và consistency |
| **RDBMS** | `UPDATE ... WHERE available >= q` trong transaction phù hợp | Số dòng cập nhật, isolation, deadlock/retry và ràng buộc DB |
| **Hệ phân tán nhiều dịch vụ** | Transaction trong một nguồn hoặc saga với trạng thái trung gian | Thứ tự, idempotency, bù trừ và invariant tức thời hay eventual |

Ví dụ, nếu trong Redis giữ cả hai bộ đếm trong một hash và dùng script server-side để kiểm tra số lượng rồi tăng/giảm, ta cũng có thể tạo một phép chuyển trạng thái không bị chen giữa bởi client khác trong phạm vi bảo đảm của Redis. Tuy nhiên, một lệnh `HGET` ở client rồi hai lệnh `HINCRBY` riêng **không tương đương** với việc kiểm tra và cập nhật nguyên tử.

Trong Cassandra, việc chỉ viết nhiều câu `UPDATE` không chứng minh được invariant tương đương; cần xét khả năng conditional update/lightweight transaction của phiên bản sử dụng và thiết kế partition. Không nên khẳng định một cơ chế nhất quán tồn tại chỉ vì DBMS thuộc họ wide-column.

**Quy tắc:** đọc tài liệu bảo đảm của DBMS cụ thể, đối chiếu với đơn vị dữ liệu tạo thành invariant, rồi mới chọn cách viết phép cập nhật.

## 16. Một chứng minh tối thiểu nên ghi đủ những thành phần nào?

Để một nhóm khác có thể hiểu và phản biện được, hãy ghi rõ:

| Thành phần | Nội dung trong ví dụ |
| --- | --- |
| **Đối tượng** | Tồn kho của một cặp warehouse–SKU |
| **Bất biến** | `available >= 0`, `reservedTotal >= 0`, tổng bằng `capacity` |
| **Giả định ban đầu** | `capacity=5`, `available=5`, `reservedTotal=0` |
| **Phạm vi dữ liệu** | Một document inventory có `_id` duy nhất |
| **Đầu vào hợp lệ** | `quantity` là số nguyên dương trong miền số hỗ trợ |
| **Phép cập nhật** | Điều kiện `available >= quantity`, cùng lúc trừ available và cộng reserved |
| **Nguyên tử** | Một cập nhật document của MongoDB |
| **Thất bại hợp lệ** | Điều kiện không khớp thì không thay đổi dữ liệu |
| **Đồng thời** | Các cập nhật cạnh tranh trên cùng document không cùng sử dụng snapshot kiểm tra cũ |
| **Lập luận** | Base case + hai trường hợp trong inductive step |
| **Kiểm thử** | Thành công, không đủ hàng, biên, đầu vào sai, hai request đồng thời |
| **Giới hạn** | Chưa chứng minh idempotency, order/payment consistency, restock/cancel |

Một khẳng định mơ hồ như **“MongoDB ghi nguyên tử nên sẽ không oversell”** là chưa đủ. Tính nguyên tử chỉ có ích nếu **cả điều kiện bảo vệ và các trường phải cập nhật** được đưa vào đúng đơn vị nguyên tử.

## 17. Từ yêu cầu nghiệp vụ đến thiết kế có thể chứng minh

Có thể đi theo trình tự sau:

~~~text
Yêu cầu:
  Không cấp phát vượt tồn kho
           │
           ▼
Phát biểu invariant:
  available >= 0
  available + reservedTotal = capacity
           │
           ▼
Xác định nhóm dữ liệu:
  Một cặp warehouseId + sku
           │
           ▼
Chọn ranh giới nguyên tử:
  Một document inventory
           │
           ▼
Định nghĩa phép chuyển:
  q > 0 và available >= q
  $inc available -q, reservedTotal +q
           │
           ▼
Chứng minh base + inductive step
           │
           ▼
Chạy các tình huống quan sát:
  q vừa đủ, q quá lớn, concurrent, retry
           │
           ▼
Ghi rõ những invariant chưa được chứng minh
~~~

Quy trình này không bắt đầu từ câu “dùng collection nào” hay “có index gì”. Nó bắt đầu từ **điều phải luôn đúng**. Sau khi có điều kiện đó, việc nhóm dữ liệu, chọn model và viết phép cập nhật mới có cơ sở.

## 18. Bài tập áp dụng

### Bài 1 — Chứng minh giới hạn 10 ghế

Một phòng học có 10 ghế. Hệ thống lưu:

~~~json
{
  "_id": "room-1",
  "capacity": 10,
  "available": 10,
  "bookedTotal": 0
}
~~~

Hãy viết:

1. Invariant về `available`, `bookedTotal`, `capacity`.
2. Điều kiện của thao tác `book(q)`.
3. Công thức cập nhật khi chấp nhận.
4. Lập luận vì sao đặt 7 ghế và 5 ghế đồng thời không thể cùng thành công nếu điều kiện và cập nhật là nguyên tử.

**Gợi ý:** đây là cùng dạng với ví dụ cấp phát tồn kho. Khi `capacity=10` và tổng yêu cầu bằng 12, có thể chỉ một yêu cầu được chấp nhận; số còn lại không âm.

### Bài 2 — Tìm lỗi trong phép cập nhật

Một lập trình viên viết:

~~~javascript
await inventory.updateOne(
  { _id: "WH-1:SKU-100" },
  { $inc: { available: -quantity, reservedTotal: quantity } }
);
~~~

Lệnh này đã cập nhật hai trường trong một document. Nó còn thiếu điều kiện nào để bảo vệ bất biến không âm? Validation đầu vào nào phải có?

**Gợi ý:** nguyên tử không đồng nghĩa có điều kiện đủ hàng; cần `available >= quantity` và `quantity` hợp lệ, dương, nguyên.

### Bài 3 — Tìm lỗi trong kiểm tra ở client

Một request đọc `available=5`, kiểm tra `q=4` hợp lệ rồi ghi tồn thành 1. Một request khác đọc cùng giá trị 5, kiểm tra `q=3` hợp lệ rồi ghi tồn thành 2.

Vì sao dữ liệu cuối có thể trông không âm nhưng nghiệp vụ vẫn đã cấp phát quá mức?

**Gợi ý:** hai request đều báo thành công dựa trên snapshot cũ. Tổng lượng đã hứa vượt 5, còn trạng thái cuối bị lost update.

### Bài 4 — Hủy reservation

Giả sử thêm phép `release(q)`:

\[
available'=available+q,\quad
reservedTotal'=reservedTotal-q
\]

Hãy chỉ ra điều kiện cần để không làm `reservedTotal` âm. Sau đó giải thích vì sao điều kiện ấy chưa đảm bảo một `reservationId` chỉ được hủy một lần.

**Gợi ý:** tổng số đã giữ đủ không chứng minh đúng reservation cụ thể đang ở trạng thái có thể hủy.

### Bài 5 — Giới hạn theo khách hàng

Hệ thống đặt quy tắc “mỗi khách chỉ được giữ tối đa 2 chiếc SKU-100”. Vì sao document chỉ có `available` và `reservedTotal` chưa đủ chứng minh quy tắc này?

**Gợi ý:** cần biết **mỗi khách hiện đang giữ bao nhiêu**, chứ không chỉ tổng kho. Đó là bất biến khác, có thể cần một nhóm dữ liệu hoặc đường cập nhật khác.

### Bài 6 — Tổng tồn nhiều kho

SKU-100 có hai kho, mỗi kho một document. Hệ thống cam kết tổng hàng chưa cấp phát không bao giờ âm và tổng giữ hàng toàn mạng không vượt tổng sức chứa. Nếu ứng dụng chỉ cập nhật một kho tại một thời điểm, có thể suy ra bất biến toàn hệ thống từ bất biến của từng kho trong những điều kiện nào?

**Gợi ý:** nếu hai kho là các tập hàng không chồng lặp, mọi phép cập nhật giữ từng kho hợp lệ và không có chuyển hàng không được phối hợp, tổng các số không âm cũng không âm. Nhưng khi có **chuyển hàng, phân bổ trùng một hàng ở hai kho hoặc quy tắc global quota**, cần bổ sung điều kiện và cơ chế phối hợp.

### Bài 7 — Retry sau timeout

Client gọi `reserve(2)`, DBMS đã commit nhưng phản hồi mất. Client gọi lại. Invariant `available >= 0` có thể vẫn đúng hay không? Có bất biến nghiệp vụ nào khác bị vi phạm?

**Gợi ý:** số tồn vẫn có thể không âm, nhưng cùng một request có thể bị cấp phát hai lần. Cần ID request ổn định và idempotency.

### Bài 8 — Chọn phạm vi nguyên tử

Giả sử có hai yêu cầu:

1. “Không bán vượt số lượng SKU ở một kho.”
2. “Không hoàn tất thanh toán nếu chưa tạo đơn và giữ tồn tương ứng ở hai dịch vụ khác nhau.”

Hãy xác định nhóm dữ liệu liên quan và xem **một document inventory** có đủ bảo đảm cả hai không.

**Gợi ý:** yêu cầu thứ nhất có thể được bảo vệ tại một document; yêu cầu thứ hai cần cơ chế phối hợp giữa nhiều trạng thái/dịch vụ và xác định rõ trạng thái trung gian.

## 19. Checklist dùng lại cho một invariant mới

Khi gặp một bài toán khác, có thể lập bản đặc tả:

~~~yaml
invariantId: INVENTORY-NO-OVERALLOCATE
businessMeaning: "Do not allocate more units than capacity"
entityBoundary: "One warehouse + one SKU"
storageExample: "One MongoDB document"
state:
  - capacity
  - available
  - reservedTotal
initialValidity:
  - "available >= 0"
  - "reservedTotal >= 0"
  - "available + reservedTotal == capacity"
allowedOperations:
  - name: reserve
    precondition: "quantity positive integer and available >= quantity"
    atomicChange:
      - "available -= quantity"
      - "reservedTotal += quantity"
  - name: reject
    precondition: "insufficient available or invalid request"
    atomicChange: "none"
atomicityBoundary: "Single document conditional update"
concurrencyAssumption: "Competing writes obey the DBMS single-document atomicity"
excludedForThisProof:
  - "Retry idempotency without request IDs"
  - "Cancellation and restock"
  - "Order and payment consistency"
  - "Arbitrary administrative writes"
tests:
  - "Initial state"
  - "Allocate exact available"
  - "Reject excessive quantity"
  - "Reject invalid inputs"
  - "Competing requests whose sum exceeds capacity"
evidence:
  reasoning: "Base case and transition preservation"
  runtimeCheck: "Observed tests in an isolated environment"
~~~

Đây là **mẫu tài liệu thiết kế**, không phải cấu hình MongoDB tự thực thi. Trong hệ thống thật, cần bổ sung quyền ghi, dữ liệu đầu vào, phiên bản schema, thao tác khôi phục, quy tắc retry, giới hạn số học và các đường cập nhật khác.

## 20. Kết luận

Muốn chứng minh một bất biến được giữ trong NoSQL, phải làm rõ **điều kiện trạng thái**, **phạm vi dữ liệu**, **tập phép chuyển** và **bảo đảm atomicity thực sự của hệ quản trị**.

Ví dụ cấp phát tồn kho đã cho thấy một hướng thiết kế cụ thể:

- Nhóm ba trường `capacity`, `available`, `reservedTotal` của một SKU–kho vào một document.
- Khởi tạo từ trạng thái thỏa `available >= 0` và `available + reservedTotal = capacity`.
- Chỉ chấp nhận `quantity > 0` và cập nhật khi `available >= quantity`.
- Kiểm tra điều kiện và giảm/tăng hai bộ đếm **trong một thao tác nguyên tử**.
- Chứng minh bằng quy nạp rằng mỗi thao tác được phép không đưa document ra ngoài tập trạng thái hợp lệ.
- Kiểm thử các trường hợp biên và cạnh tranh, đồng thời thừa nhận rằng kiểm thử chỉ là bằng chứng thực nghiệm.
- Ghi rõ rằng **idempotency, đơn hàng, thanh toán, hủy giữ hàng và dữ liệu nhiều document** là những yêu cầu khác cần thiết kế riêng.

**Một ví dụ tối thiểu có giá trị không phải vì nó bao phủ mọi nghiệp vụ, mà vì nó chỉ ra chính xác điều gì được chứng minh, tại sao đúng và phạm vi nào chưa được bảo đảm.** Đây là cách dùng tư duy về **nhóm dữ liệu và bất biến** để chọn một cấu trúc NoSQL vừa phục vụ truy vấn vừa bảo vệ tính đúng đắn khi có nhiều thao tác đồng thời.
