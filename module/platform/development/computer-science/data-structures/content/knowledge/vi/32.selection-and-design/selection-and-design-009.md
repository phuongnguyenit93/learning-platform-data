# Duy trì nhiều chỉ mục trên cùng tập dữ liệu và tính nhất quán khi cập nhật

Một hệ thống quản lý sản phẩm thường phải trả lời nhiều câu hỏi về **cùng một tập bản ghi**:

- “Lấy sản phẩm có mã `SKU-104`.”
- “Liệt kê tất cả sản phẩm thuộc danh mục sách.”
- “Tìm sản phẩm có giá từ 100 đến 300, theo giá tăng dần.”
- “Lọc các sản phẩm có nhãn `sale`.”
- “Đếm sản phẩm đang được bán trong một danh mục.”

Không có một cách tổ chức dữ liệu đơn giản nào luôn tối ưu cho toàn bộ phép toán đó. Bảng băm theo mã giúp tra cứu chính xác nhanh; cây cân bằng theo giá hỗ trợ khoảng có thứ tự; các tập ID theo danh mục hoặc nhãn giúp lọc. Vì thế, ta thường cần **nhiều chỉ mục cùng mô tả một tập thực thể**.

Đổi lại, một thao tác cập nhật duy nhất có thể phải sửa nhiều cấu trúc. Nếu một chỉ mục đã phản ánh giá mới nhưng chỉ mục khác vẫn giữ dữ liệu cũ, hệ thống có thể trả **những kết quả mâu thuẫn**. Trong chương **Lựa chọn và thiết kế**, việc chọn đúng chỉ mục phải đi cùng việc định nghĩa **bất biến, thứ tự cập nhật, tính nguyên tử và chi phí duy trì chỉ mục**.

Bài học xây dựng một mô hình tự chứa từ nền tảng mảng, bảng băm và cây; chỉ ra cách cập nhật, đọc nhất quán, kiểm thử và quyết định khi nào nên giữ nhiều chỉ mục.

## 1. Một tập bản ghi, nhiều đường truy cập

Giả sử mỗi sản phẩm có các trường:

```text
Product {
    sku:       string   // mã duy nhất, bất biến trong vòng đời
    category:  string   // danh mục
    price:     integer  // giá tính bằng đơn vị nguyên nhỏ nhất
    tags:      set<string>
    name:      string
}
```

Ta muốn triển khai những API khác nhau:

| API | Khóa/điều kiện truy vấn | Cấu trúc gợi ý |
| --- | --- | --- |
| `getBySku(sku)` | Bằng đúng một mã duy nhất | `HashMap<SKU, Product>` |
| `listByCategory(cat)` | Bằng một danh mục, có nhiều kết quả | `HashMap<Category, Set<SKU>>` |
| `rangeByPrice(lo,hi)` | Khoảng giá, có thứ tự | Cây tìm kiếm cân bằng theo `(price,sku)` |
| `listByTag(tag)` | Một nhãn có thể xuất hiện trong nhiều sản phẩm | Chỉ mục đảo `HashMap<Tag, Set<SKU>>` |
| `listAfterPrice(cursor,k)` | Tiếp tục duyệt theo khóa có thứ tự | Cây có thứ tự + cursor theo `(price,sku)` |

**Chỉ mục (index)** là một cấu trúc cho phép tìm nhanh một tập bản ghi theo một điều kiện. Một chỉ mục có thể chứa bản ghi đầy đủ, bản sao một số thuộc tính hoặc chỉ chứa ID/tham chiếu đến bản ghi chính.

Trong bài này ta chọn **một nguồn bản ghi chuẩn (source of truth)**:

```text
bySku: HashMap<SKU, Product>
```

Các cấu trúc còn lại là **chỉ mục phụ (secondary indexes)**, được suy ra từ `bySku`:

```text
byCategory: HashMap<Category, Set<SKU>>
byPrice:    BalancedBST<(Price, SKU)>
byTag:      HashMap<Tag, Set<SKU>>
```

Bản ghi chính giữ giá trị có thẩm quyền; chỉ mục phụ giữ đường dẫn tìm kiếm. Nhờ vậy, truy vấn theo danh mục/giá/nhãn không cần quét mọi sản phẩm.

### 1.1. Vì sao chỉ mục phụ thường lưu ID?

Nếu `byCategory["books"]` chứa các `SKU`, ta có thể tra `bySku[sku]` để lấy bản ghi hiện hành. Điều này tránh sao chép toàn bộ đối tượng sản phẩm vào mỗi chỉ mục, nhưng thêm một bước *lookup*.

Nếu mỗi chỉ mục lại giữ một **bản sao dữ liệu**, cập nhật tên, giá hoặc thuộc tính khác phải đồng bộ mọi bản sao; chi phí bộ nhớ và nguy cơ dữ liệu cũ tăng lên. Lưu ID giúp giảm trùng lặp dữ liệu, tuy nhiên **không tự bảo đảm tính nhất quán**: các ID được thêm/xóa vào tập phụ vẫn phải chính xác.

Một ngoại lệ hợp lý là **covering index**, lưu sẵn những thuộc tính hay truy vấn để không cần tra bản ghi gốc. Đây là đánh đổi giữa tốc độ đọc, kích thước chỉ mục và chi phí làm mới dữ liệu.

### 1.2. Chỉ mục không thay thế định danh

`SKU` là định danh logic của sản phẩm; vị trí trong mảng, bucket trong hash map hoặc nút trong cây chỉ là chi tiết lưu trữ. Khi cây xoay, bảng băm rehash hoặc dãy sản phẩm sắp xếp lại, sản phẩm **không đổi danh tính**.

Nếu ID có thể tái sử dụng cho thực thể mới, cần quy tắc vòng đời hoặc phiên bản để không dùng nhầm tham chiếu cũ. Một thiết kế thường dễ quản lý hơn nếu ID không đổi trong suốt vòng đời bản ghi.

## 2. Thiết kế đúng từ bất biến hai chiều

Gọi `P` là ánh xạ `bySku`; `C` là chỉ mục danh mục; `R` là chỉ mục giá; `T` là chỉ mục nhãn. Gọi `live(P)` là tập tất cả ID còn tồn tại trong bản ghi chính.

**Bất biến của dữ liệu chính (I0):**

- Mỗi SKU đang hoạt động ánh xạ đến đúng một `Product`.
- `P[sku].sku == sku`.
- Những trường được dùng trong khóa chỉ mục có ngữ nghĩa so sánh/chuẩn hóa nhất quán.

**Bất biến danh mục (I1):**

```text
sku ∈ C[cat]  ⇔  sku ∈ live(P) và P[sku].category == cat
```

Dấu `⇔` mang ý nghĩa **cả hai chiều**. Không chỉ mọi bản ghi hiện hành phải có trong danh mục đúng; chỉ mục cũng **không được giữ SKU đã xóa, SKU sai danh mục hoặc SKU không tồn tại**.

**Bất biến giá (I2):**

```text
R == { (P[sku].price, sku) | sku ∈ live(P) }
```

Mỗi bản ghi chính tương ứng **đúng một** khóa giá trong cây có thứ tự. Nếu hai sản phẩm cùng giá, khóa ghép `(price,sku)` vẫn phân biệt được nhờ SKU duy nhất.

**Bất biến nhãn (I3):**

```text
sku ∈ T[tag]  ⇔  sku ∈ live(P) và tag ∈ P[sku].tags
```

Một SKU có thể xuất hiện ở nhiều tập nhãn nhưng không bị lặp trong cùng một tập vì dùng `Set`.

**Bất biến về số lượng (I4):**

```text
|P| = tổng theo cat của |C[cat]|  // nếu mỗi sản phẩm có đúng một category
|P| = |R|
```

Đẳng thức thứ nhất chỉ đúng nếu mỗi bản ghi có **một danh mục hợp lệ duy nhất** và các tập danh mục không chồng nhau. Đối với nhãn, tổng kích thước các tập `T[tag]` có thể **lớn hơn** số sản phẩm vì một sản phẩm mang nhiều nhãn.

### 2.1. Ví dụ kiểm tra bất biến

Giả sử hiện có:

| SKU | Category | Price | Tags |
| --- | --- | ---: | --- |
| `A10` | books | 120 | new, sale |
| `B20` | tools | 80 | new |
| `C30` | books | 120 | gift |

Các chỉ mục phụ phải chứa:

```text
byCategory:
    books -> {A10, C30}
    tools -> {B20}

byPrice (theo thứ tự):
    (80, B20)
    (120, A10)
    (120, C30)

byTag:
    new  -> {A10, B20}
    sale -> {A10}
    gift -> {C30}
```

Nếu `A10` đổi `category` từ `books` sang `tools` và giá từ 120 xuống 70, thì trạng thái hợp lệ sau cập nhật là:

```text
byCategory:
    books -> {C30}
    tools -> {A10, B20}

byPrice:
    (70, A10)
    (80, B20)
    (120, C30)
```

Bản ghi chính cũng phải có `category=tools, price=70`. Nếu chỉ thay `bySku` mà không xóa `(120,A10)` khỏi cây, truy vấn “giá trên 100” có thể trả A10 mặc dù giá hiện hành đã là 70.

**Tính đúng đắn nằm ở sự phù hợp giữa mọi cấu trúc, không ở tính đúng đắn riêng lẻ của từng map/cây.**

## 3. Chọn khóa chỉ mục và chính sách trùng lặp

Một bản ghi có thể được tìm theo nhiều thuộc tính, nhưng các thuộc tính không có cùng tính duy nhất.

| Thuộc tính | Có thể trùng? | Biểu diễn thường gặp | Cần xác định |
| --- | --- | --- | --- |
| `sku` | Không, nếu là khóa chính | `HashMap<SKU, Product>` | Quy tắc cấp ID, cập nhật và xóa |
| `category` | Có | `Map<Category, Set<SKU>>` | Tập ID trả về có cần thứ tự không |
| `price` | Có | `BalancedBST<(Price,SKU)>` | Khóa ghép phá hòa, khoảng đóng/mở |
| `tag` | Có; mỗi sản phẩm có thể có nhiều nhãn | `Map<Tag, Set<SKU>>` | Chuẩn hóa nhãn, thêm/xóa nhãn |
| `name` | Có | Trie/chỉ mục chuỗi sắp/inverted index | Tiền tố hay từ khóa đầy đủ, chuẩn hóa Unicode |

**Không tạo cây tập hợp chỉ theo `price` nếu API cần giữ nhiều sản phẩm cùng mức giá** và cấu trúc không hỗ trợ khóa trùng. Dùng khóa ghép `(price,sku)` hoặc multimap với quy tắc trùng lặp rõ ràng.

Với chỉ mục nhãn, `tags={"new","sale"}` phải tạo **hai liên kết** đến cùng SKU. Xóa sản phẩm cần xóa tất cả các liên kết tương ứng, nhưng điều đó không đồng nghĩa xóa nhãn khỏi các sản phẩm khác.

Nếu chỉ mục dùng chuỗi không phân biệt hoa thường, phải chuẩn hóa **cùng một cách khi ghi và khi hỏi**; ví dụ dùng một chính sách Unicode/case-fold đã xác định. Nếu dữ liệu chính lưu tên gốc, chỉ mục có thể lưu khóa chuẩn hóa để tìm, nhưng cần nêu quy tắc hiển thị/so sánh và xử lý các chuỗi khác nhau chuẩn hóa về cùng một giá trị.

## 4. Thêm bản ghi: cập nhật tất cả chỉ mục liên quan

Giả sử thêm sản phẩm `D40` vào danh mục `books`, giá 90, nhãn `sale`.

Một thao tác logic `create(product)` cần làm:

```text
create(p):
    require p.sku không tồn tại
    validate(p)

    // Bắt đầu một đơn vị cập nhật nguyên tử
    bySku[p.sku] = p
    byCategory[p.category].add(p.sku)
    byPrice.insert((p.price, p.sku))
    for tag in p.tags:
        byTag[tag].add(p.sku)
    // Hoàn tất đơn vị cập nhật
```

Nếu thao tác hoàn tất thành công, tất cả bất biến I0–I3 phải đúng. Nếu chèn vào `byPrice` thất bại vì thiếu bộ nhớ hoặc gặp lỗi triển khai, không thể để lại sản phẩm trong `bySku` và danh mục nhưng thiếu cây giá rồi báo “thêm thất bại”.

### 4.1. Kiểm tra trước khi sửa

Trước khi ghi:

1. Kiểm tra tính hợp lệ của SKU, giá, danh mục và nhãn.
2. Kiểm tra ràng buộc duy nhất của khóa chính.
3. Xác định chính xác các khóa phụ sẽ tạo.
4. Dự kiến các thất bại có thể xảy ra: cấp phát, giới hạn số lượng, khóa xung đột, lỗi lưu trữ.

**Kiểm tra trước không thay thế tính nguyên tử.** Với hai luồng, cả hai có thể cùng nhìn thấy `sku` chưa tồn tại rồi cùng thêm nếu kiểm tra và ghi không nằm trong cùng vùng đồng bộ/giao dịch.

### 4.2. Không công bố trạng thái cập nhật dở dang

Có hai nguyên tắc cơ bản:

- **Nguyên tử về mặt logic:** sau một thao tác thành công, tất cả chỉ mục mô tả cùng phiên bản dữ liệu; nếu thất bại, các thay đổi chưa được công nhận không được tồn tại nửa chừng.
- **Nguyên tử về mặt quan sát:** người đọc đồng thời không nhìn thấy trạng thái sau khi mới cập nhật một nửa chỉ mục.

Một chuỗi lệnh theo đúng thứ tự **không tự đáp ứng** hai nguyên tắc trên. Cần cơ chế phù hợp như khóa cho toàn bộ thao tác, giao dịch của hệ lưu trữ, rollback hoặc xây phiên bản mới rồi công bố khi hoàn tất.

## 5. Xóa bản ghi: loại mọi đường dẫn đến dữ liệu đã xóa

Để xóa `B20`, trước tiên phải đọc trạng thái **trước cập nhật**, vì nó cung cấp khóa để xóa khỏi các chỉ mục phụ:

```text
delete(sku):
    old = bySku.get(sku)
    if old không tồn tại:
        return NOT_FOUND

    // Một đơn vị cập nhật logic
    byCategory[old.category].remove(sku)
    byPrice.remove((old.price, sku))
    for tag in old.tags:
        byTag[tag].remove(sku)
    bySku.remove(sku)
    // Hoàn tất hoặc rollback toàn bộ
```

Nếu xóa `bySku[sku]` trước rồi mới cố đọc `price` và `category` từ bản ghi đã xóa, có thể không còn đủ thông tin để dọn chỉ mục phụ.

**Không giữ orphan entry:** một ID nằm trong `byCategory` hay `byTag` nhưng không còn tồn tại ở `bySku` là một tham chiếu mồ côi. Nếu không được xử lý, truy vấn có thể trả ID rỗng, lỗi hoặc danh sách không đúng.

**Không giữ giá cũ:** nếu `(old.price,sku)` chưa xóa khỏi cây, truy vấn khoảng có thể trả một sản phẩm đã bị xóa. Thậm chí nếu truy vấn tra lại `bySku` rồi âm thầm bỏ qua ID không tồn tại, chỉ mục vẫn hỏng và sẽ ngày càng phình to.

Nếu một sản phẩm mang `t` nhãn, xóa nó cần dọn `t` tập nhãn. Chi phí này phải được tính: giữ càng nhiều chỉ mục phụ, một lần ghi càng có nhiều việc phải làm.

## 6. Sửa bản ghi: cần cả giá trị cũ và giá trị mới

Một thao tác sửa sản phẩm thường không đụng đến mọi chỉ mục. Ta nên so từng trường và cập nhật đúng những chỉ mục có khóa thay đổi.

Ví dụ `A10` đổi:

```text
Old:
    sku=A10, category=books, price=120, tags={new, sale}

New:
    sku=A10, category=tools, price=70, tags={sale, gift}
```

Các phần phải cập nhật:

| Chỉ mục | Thao tác bắt buộc |
| --- | --- |
| `bySku` | Lưu bản ghi mới cho `A10` |
| `byCategory` | Xóa `A10` khỏi `books`, thêm vào `tools` |
| `byPrice` | Xóa `(120,A10)`, thêm `(70,A10)` |
| `byTag` | Xóa khỏi nhãn `new`; thêm vào nhãn `gift`; **giữ nguyên** trong `sale` |

Với tập nhãn:

```text
removedTags = old.tags - new.tags
addedTags   = new.tags - old.tags

for tag in removedTags:
    byTag[tag].remove(sku)
for tag in addedTags:
    byTag[tag].add(sku)
```

Ta không cần xóa toàn bộ nhãn cũ rồi thêm lại tất cả nếu chỉ một nhãn thay đổi. Kỹ thuật **tính phần chênh lệch (delta)** giảm số thao tác và tránh làm rối những cấu trúc phụ không bị ảnh hưởng.

### 6.1. Mã giả cập nhật có điều kiện

```text
update(sku, patch):
    old = bySku.get(sku)
    if old không tồn tại:
        return NOT_FOUND

    new = applyPatchToCopy(old, patch)
    validate(new)
    require new.sku == old.sku

    begin_atomic_change()

    if old.category != new.category:
        byCategory[old.category].remove(sku)
        byCategory[new.category].add(sku)

    if old.price != new.price:
        byPrice.remove((old.price, sku))
        byPrice.insert((new.price, sku))

    for tag in old.tags - new.tags:
        byTag[tag].remove(sku)
    for tag in new.tags - old.tags:
        byTag[tag].add(sku)

    bySku[sku] = new
    commit_atomic_change()
```

`begin_atomic_change` và `commit_atomic_change` là **khái niệm giao dịch**, không phải hàm có sẵn trong mảng/bảng băm/cây. Cơ chế cụ thể được phân tích ở phần tiếp theo.

### 6.2. Vì sao không nên sửa bản ghi tại chỗ trước?

Giả sử `old` là tham chiếu đến đối tượng có thể thay đổi (*mutable*). Nếu làm:

```text
old.price = 70
byPrice.remove((old.price, sku))
```

lệnh xóa đang tìm `(70,sku)` thay vì khóa cũ `(120,sku)`. Khóa cũ sẽ còn trong cây, phá I2.

Nên **lưu snapshot các trường cũ**, tạo bản ghi mới bất biến hoặc tính tất cả khóa chỉ mục cũ **trước khi sửa**. Đây không chỉ là mẹo lập trình: chỉ mục là một hàm của trạng thái dữ liệu nên cập nhật cần biết **cả trạng thái trước và sau**.

### 6.3. Đổi khóa chính cần chính sách riêng

Nếu `sku` là định danh ổn định, không nên cho sửa nó tùy ý. Nếu nghiệp vụ bắt buộc đổi SKU:

- Phải cập nhật mọi chỉ mục giữ SKU cũ.
- Phải kiểm tra SKU mới chưa được dùng.
- Các tham chiếu, liên kết hoặc bản ghi bên ngoài có thể đang giữ SKU cũ.
- Cần quyết định alias từ SKU cũ sang mới hay coi là xóa thực thể cũ và tạo thực thể mới.

Không thể chỉ thay `product.sku` rồi giả định `HashMap` và cây tự cập nhật khóa. Với nhiều hệ thống, nên tách **ID bất biến** khỏi mã hiển thị có thể đổi.

## 7. Tính nguyên tử: tránh trạng thái “nửa cũ, nửa mới”

Một thao tác cập nhật liên chỉ mục thường gồm nhiều bước. Nếu bất kỳ bước nào thất bại hoặc nếu người đọc chen vào, tính nhất quán có thể bị phá.

### 7.1. Kịch bản lỗi

Giả sử cập nhật giá của A10 từ 120 xuống 70:

```text
T0: bySku[A10].price = 120
    byPrice chứa (120,A10)

T1: byPrice xóa (120,A10)
T2: byPrice thêm (70,A10)
T3: bySku[A10].price = 70
```

Nếu một truy vấn theo khoảng giá chạy ở giữa T2 và T3, nó có thể thấy A10 dưới giá 70 trong chỉ mục nhưng khi đọc bản ghi lại thấy giá 120. Nếu chương trình lỗi giữa T1 và T2, chỉ mục giá sẽ thiếu A10.

**Thứ tự cập nhật hợp lý giúp dễ lập luận nhưng không tự tạo tính nguyên tử.**

### 7.2. Ba chiến lược thường gặp

| Chiến lược | Cách hoạt động | Phạm vi và đánh đổi |
| --- | --- | --- |
| **Khóa + ghi tại chỗ** | Khóa vùng đọc/ghi, cập nhật tất cả cấu trúc rồi mở khóa | Ngăn người đọc cùng giao thức nhìn trạng thái dở dang; vẫn cần **rollback** khi lỗi |
| **Giao dịch của hệ lưu trữ** | Đưa bản ghi và các chỉ mục vào cùng transaction, commit hoặc rollback | Phụ thuộc khả năng transaction của nơi lưu; thường phù hợp khi chỉ mục nằm trong cùng DB |
| **Copy-on-write/snapshot** | Dựng trạng thái mới ngoài trạng thái đang công bố, kiểm tra rồi thay tham chiếu snapshot | Dễ giữ bản đọc nhất quán; có thể tốn sao chép/bộ nhớ, cần đồng bộ công bố và thu hồi phiên bản |

**Khóa không tự phục hồi lỗi.** Một luồng nắm khóa rồi làm được 2/4 thao tác, gặp exception, mở khóa và trả thất bại vẫn để cấu trúc hỏng. Phải đảm bảo rollback đúng hoặc xây trạng thái mới trước khi công bố.

**Copy-on-write không tự bền vững qua mất điện.** Chỉ giữ snapshot trong RAM giúp công bố nguyên tử ở mức ứng dụng theo hợp đồng đồng bộ, không đảm bảo khôi phục sau crash của tiến trình/máy. Với dữ liệu lâu dài, cần transaction bền vững hoặc nhật ký ghi trước (*write-ahead log*) và cơ chế phục hồi đúng.

### 7.3. Rollback bằng thông tin trước cập nhật

Trong mô hình ghi tại chỗ, có thể ghi lại các thao tác đảo ngược:

```text
undoLog = []

try:
    removeFromOldCategory(sku)
    undoLog.push(() => addToOldCategory(sku))

    insertIntoNewCategory(sku)
    undoLog.push(() => removeFromNewCategory(sku))

    removeOldPriceKey(sku)
    undoLog.push(() => restoreOldPriceKey(sku))

    insertNewPriceKey(sku)
    undoLog.push(() => removeNewPriceKey(sku))

    replaceMainRecord(sku, new)
    undoLog.push(() => replaceMainRecord(sku, old))

    commit()
catch error:
    executeUndoLogInReverseOrder()
    raise error
```

Đây là **mã giả để giải thích ý tưởng**, không phải triển khai đủ cho mọi dạng lỗi. Undo có thể tự thất bại, bộ cấp phát có thể cạn, tiến trình có thể dừng trước khi rollback và các thao tác bên ngoài (gửi email, gọi API) thường không đảo ngược dễ dàng.

Trong hệ thống dữ liệu bền vững, ưu tiên dùng transaction có cơ chế rollback/recovery đã được kiểm chứng. Trong cấu trúc RAM nhỏ phục vụ học tập, copy-on-write giúp minh họa tính nhất quán mà không cần giải quyết đầy đủ các trường hợp undo thất bại.

## 8. Mã Python minh họa: chỉ mục phụ và snapshot nhất quán

Ta xây một danh mục nhỏ có ba cấu trúc:

- `by_sku: dict[SKU, Product]` — dữ liệu chính.
- `by_category: dict[Category, frozenset[SKU]]` — chỉ mục danh mục.
- `by_price: tuple[(price, sku)]` **được sắp xếp** — chỉ mục giá.

Đây là một triển khai học tập theo kiểu **copy-on-write**, không phải cây cân bằng: khi ghi, ta tạo bản sao các cấu trúc rồi công bố snapshot hoàn chỉnh. Mọi lần đọc nhận một snapshot chung; vì bản cũ không bị sửa, đọc nhiều chỉ mục từ snapshot đó không gặp trạng thái cập nhật nửa chừng.

**Giới hạn có chủ ý:** copy toàn bộ map và dãy giá làm mỗi lần ghi có chi phí `O(n)` theo số sản phẩm, chưa kể cấp phát bộ nhớ. Điều này thuận tiện để minh họa **tính đúng đắn của cập nhật nhiều chỉ mục**, nhưng không phải lựa chọn tối ưu cho danh mục lớn có nhiều lần ghi. Phần sau sẽ chỉ ra cách dùng giao dịch và cây cân bằng để cải thiện.

```python
from bisect import bisect_left, insort
from dataclasses import dataclass, replace
from threading import RLock


@dataclass(frozen=True)
class Product:
    sku: str
    category: str
    price: int  # đơn vị tiền nhỏ nhất, nguyên và không âm


@dataclass(frozen=True)
class Snapshot:
    by_sku: dict
    by_category: dict  # category -> frozenset[SKU]
    by_price: tuple    # sorted tuples: (price, sku)


class Catalog:
    def __init__(self):
        self._lock = RLock()
        self._state = Snapshot({}, {}, ())

    @staticmethod
    def _validate(product):
        if not isinstance(product.sku, str) or not product.sku:
            raise ValueError("SKU must be a nonempty string")
        if not isinstance(product.category, str) or not product.category:
            raise ValueError("category must be a nonempty string")
        if type(product.price) is not int or product.price < 0:
            raise ValueError("price must be a nonnegative integer")

    def _snapshot(self):
        # Lấy một phiên bản đã công bố; không phơi bày cho người gọi.
        with self._lock:
            return self._state

    def _replace_locked(self, old, new):
        # Điều kiện: người gọi đang giữ self._lock.
        # Không sửa bất kỳ cấu trúc nào thuộc self._state cũ.
        s = self._state
        rows = dict(s.by_sku)
        cats = {key: set(ids) for key, ids in s.by_category.items()}
        prices = list(s.by_price)

        if old is not None:
            del rows[old.sku]
            cats[old.category].remove(old.sku)
            if not cats[old.category]:
                del cats[old.category]

            old_key = (old.price, old.sku)
            i = bisect_left(prices, old_key)
            if i == len(prices) or prices[i] != old_key:
                raise AssertionError("inconsistent old price index")
            prices.pop(i)

        if new is not None:
            rows[new.sku] = new
            cats.setdefault(new.category, set()).add(new.sku)
            insort(prices, (new.price, new.sku))

        # Chỉ công bố khi xây dựng toàn bộ trạng thái mới thành công.
        self._state = Snapshot(
            rows,
            {key: frozenset(ids) for key, ids in cats.items()},
            tuple(prices),
        )

    def create(self, product):
        self._validate(product)
        with self._lock:
            if product.sku in self._state.by_sku:
                raise ValueError("duplicate SKU")
            self._replace_locked(None, product)

    def update(self, sku, *, category=None, price=None):
        with self._lock:
            old = self._state.by_sku.get(sku)
            if old is None:
                raise KeyError(sku)

            new = replace(
                old,
                category=old.category if category is None else category,
                price=old.price if price is None else price,
            )
            self._validate(new)
            self._replace_locked(old, new)

    def delete(self, sku):
        with self._lock:
            old = self._state.by_sku.get(sku)
            if old is None:
                raise KeyError(sku)
            self._replace_locked(old, None)

    def get(self, sku):
        s = self._snapshot()
        return s.by_sku.get(sku)

    def list_category(self, category):
        s = self._snapshot()
        ids = s.by_category.get(category, frozenset())
        # Sắp ID để kết quả có thứ tự rõ ràng, không dựa vào set.
        return [s.by_sku[sku] for sku in sorted(ids)]

    def range_price(self, lo, hi):
        if lo > hi:
            return []
        s = self._snapshot()
        i = bisect_left(s.by_price, (lo, ""))
        result = []
        while i < len(s.by_price):
            price, sku = s.by_price[i]
            if price > hi:
                break
            result.append(s.by_sku[sku])
            i += 1
        return result

    def check_invariants(self):
        s = self._snapshot()
        expected_categories = {}
        expected_prices = []
        for sku, product in s.by_sku.items():
            assert product.sku == sku
            expected_categories.setdefault(product.category, set()).add(sku)
            expected_prices.append((product.price, sku))

        actual_categories = {
            category: set(ids)
            for category, ids in s.by_category.items()
        }
        assert actual_categories == expected_categories
        assert list(s.by_price) == sorted(expected_prices)
        return True
```

Trong mã này:

- `Product` bất biến theo `@dataclass(frozen=True)` nên cập nhật phải tạo một `Product` mới. Điều đó tránh lỗi sửa `price` trước khi xóa khóa giá cũ.
- Trạng thái `Snapshot` chỉ được tạo từ **bản sao**; các dict chứa bên trong được coi là chỉ đọc sau khi công bố và không bao giờ trả trực tiếp cho người dùng. `frozen=True` chỉ khóa phép gán thuộc tính cấp cao, **không biến dict lồng bên trong thành bất biến tuyệt đối**; hợp đồng không sửa snapshot cũ là phần bắt buộc của thiết kế.
- Một lần `update` có thể thay cả danh mục và giá trong **cùng snapshot mới**.
- Lock bảo vệ việc chọn trạng thái cũ, kiểm tra điều kiện và công bố trạng thái mới. Phương thức đọc chỉ giữ lock khi lấy tham chiếu snapshot; sau đó dùng một trạng thái mà các lời ghi về sau không sửa tại chỗ.
- Nếu việc xây bản sao, xóa khóa cũ hoặc chèn khóa mới ném exception **trước bước gán `self._state`**, snapshot cũ vẫn không bị thay đổi.

### 8.1. Kiểm chứng trên dữ liệu cụ thể

```python
catalog = Catalog()
catalog.create(Product("A10", "books", 120))
catalog.create(Product("B20", "tools", 80))
catalog.create(Product("C30", "books", 120))

assert catalog.check_invariants()
assert [p.sku for p in catalog.list_category("books")] == ["A10", "C30"]
assert [p.sku for p in catalog.range_price(100, 120)] == ["A10", "C30"]

# Một thao tác logic sửa cả hai đường truy cập.
catalog.update("A10", category="tools", price=70)
assert catalog.check_invariants()
assert [p.sku for p in catalog.list_category("books")] == ["C30"]
assert [p.sku for p in catalog.list_category("tools")] == ["A10", "B20"]
assert [p.sku for p in catalog.range_price(70, 90)] == ["A10", "B20"]

# Xóa khỏi nguồn chính và toàn bộ chỉ mục phụ.
catalog.delete("B20")
assert catalog.get("B20") is None
assert [p.sku for p in catalog.range_price(0, 100)] == ["A10"]
assert catalog.check_invariants()
```

Mã ví dụ không chạy trong bước tạo nội dung của bài này. Đây là mã minh họa để người học có thể tự chạy và mở rộng kiểm thử; nó không mô phỏng lỗi mất điện hay đảm bảo tính bền vững dữ liệu qua tiến trình.

### 8.2. Phân tích chi phí đúng với mã trên

Gọi `n` là số sản phẩm:

| Phép toán | Chi phí dự kiến trong bản minh họa |
| --- | --- |
| `get(sku)` | Trung bình/kỳ vọng `O(1)` của dict, cộng chi phí lock |
| `list_category(cat)` trả `k` bản ghi | Tìm tập ID trung bình `O(1)`, sắp `O(k log k)`, lấy `k` bản ghi trung bình `O(k)` |
| `range_price(lo,hi)` trả `k` bản ghi | Tìm biên `O(log n)` lần so sánh, duyệt `O(k)` phần tử |
| `create/update/delete` | **`O(n)`** do copy toàn bộ dữ liệu/chỉ mục và cập nhật mảng giá có thể dịch phần tử |
| `check_invariants()` | Chủ yếu `O(n log n)` do sắp danh sách khóa giá |
| Bộ nhớ | `O(n)` thường trực cho dữ liệu/chỉ mục; một lần ghi có thể tạm giữ **hai snapshot** `O(n)` |

Ở đây `range_price` được áp dụng trên `tuple` đã sắp nên hiệu quả đọc tốt; **ghi vào dãy đã sắp** có chi phí tuyến tính. Muốn ghi nhanh mà vẫn hỗ trợ khoảng, một cây tự cân bằng là lựa chọn phù hợp hơn, nhưng phần đồng bộ/giao dịch vẫn phải giải quyết.

Mã minh họa dùng snapshot cấu trúc liên quan tới trạng thái sản phẩm, không bao gồm cache ngoài, hệ thống tìm kiếm, thông báo hoặc các kho dữ liệu khác. Một transaction trong RAM **không mở rộng nguyên tử tự động sang các dịch vụ ngoài tiến trình**.

## 9. Cấu trúc hiệu quả hơn khi cập nhật liên tục

Nếu tải công việc có nhiều lần ghi, copy toàn bộ `O(n)` như ví dụ trên có thể tốn kém. Hãy giữ các chỉ mục có khả năng cập nhật cục bộ:

```text
bySku:      HashMap<SKU, Product>
byCategory: HashMap<Category, HashSet<SKU>>
byPrice:    BalancedBST<(Price, SKU)>
byTag:      HashMap<Tag, HashSet<SKU>>
```

Với `n` sản phẩm, `t` nhãn của một sản phẩm và giả định hash được kiểm soát:

| Hoạt động | Chi phí phần cấu trúc dữ liệu thường gặp |
| --- | --- |
| Tìm chính xác theo SKU | Kỳ vọng `O(1)` |
| Thêm bản ghi mới | Kỳ vọng khoảng `O(1+t)` cho map/set, cộng `O(log n)` chèn cây |
| Sửa giá một sản phẩm | Xóa khóa giá cũ + chèn khóa giá mới: `O(log n)` mỗi lần |
| Sửa danh mục | Xóa/thêm ID trong hai tập: kỳ vọng `O(1)` cho các thao tác map/set |
| Sửa nhãn | Kỳ vọng `O(|removedTags|+|addedTags|)` nếu đã có hai tập chênh lệch; tính thêm chi phí tạo chênh lệch |
| Xóa bản ghi | Kỳ vọng `O(t)` dọn nhãn, `O(log n)` xóa cây và các thao tác map/set |
| Liệt kê `k` bản ghi thuộc khoảng giá | `O(log n+k)` với bộ duyệt cây phù hợp, cộng chi phí lấy bản ghi theo ID |
| Bộ nhớ | `O(n + \sum |tags(product)|)` cho các mục chỉ mục trong mô hình đơn giản, ngoài dữ liệu và overhead triển khai |

Các công thức là chi phí **thuật toán bên trong cấu trúc**, không bao gồm thời gian chờ lock, I/O, giao dịch, log bền vững hoặc các bản snapshot đang được giữ. Nếu hash map có rehash và va chạm, phải phân biệt bảo đảm kỳ vọng/khấu hao với trường hợp xấu của từng thao tác.

**Lưu ý:** nếu có `t` nhãn và cần tính `removedTags`/`addedTags`, việc tạo tập chênh lệch thường phải duyệt các tập nhãn cũ/mới, nên chi phí tổng của thao tác sửa nhãn phụ thuộc cả kích thước hai tập, không chỉ số nhãn thực sự thay đổi.

### 9.1. Nhiều chỉ mục làm tăng độ khuếch đại ghi

Một bản ghi thay đổi có thể buộc hệ thống thực hiện nhiều lần sửa chỉ mục (*write amplification*). Khi thêm một sản phẩm có 20 nhãn, chỉ mục nhãn cần thêm tới 20 liên kết. Nếu tạo thêm các chỉ mục theo nhà cung cấp, trạng thái, thời gian và nhiều trường khác, chi phí ghi và bộ nhớ lại tăng.

Có thể dùng mô hình:

```text
T_write ≈ T_validate
        + T_primary
        + Σ T_secondary_index_affected
        + T_transaction_or_sync

M_index ≈ tổng bộ nhớ tất cả chỉ mục phụ
```

Không có lý do để lập chỉ mục cho **mọi trường**. Chỉ giữ các chỉ mục mà lợi ích ở truy vấn thường gặp đủ bù cho chi phí cập nhật, xây dựng, kiểm tra và bộ nhớ.

### 9.2. Chỉ mục tổng hợp và dữ liệu đếm cũng phải nhất quán

Ví dụ có `countByCategory[cat]` để trả số sản phẩm ngay trong `O(1)`. Khi thêm/xóa hoặc đổi danh mục, phải cập nhật bộ đếm tương ứng.

Bất biến:

```text
countByCategory[cat] == |byCategory[cat]|
```

Nếu một giao dịch thêm bản ghi thành công nhưng quên tăng bộ đếm, truy vấn đếm sẽ sai dù chỉ mục danh mục còn đúng. Một số hệ thống chấp nhận đếm **gần đúng hoặc cập nhật chậm**, nhưng hợp đồng API phải nói rõ; không được vừa hứa đếm chính xác vừa để bộ đếm lệch tùy ý.

### 9.3. Chỉ mục theo mảng vị trí cần thận trọng

Nếu một map `sku → arrayIndex` trỏ tới mảng bản ghi, việc chèn/xóa/sắp lại làm thay chỉ số có thể kéo theo cập nhật nhiều ánh xạ. Có thể dùng ô cố định hoặc *generational handle* để tránh truy cập nhầm sau khi tái sử dụng vị trí; tuy nhiên vẫn phải xác định vòng đời ID và mức ổn định của tham chiếu.

Đối với dữ liệu có nhiều chỉ mục, **ID logic ổn định** thường giúp tách cách truy cập khỏi vị trí lưu trữ cụ thể.

## 10. Đọc nhất quán khi có nhiều thao tác đồng thời

Ngay cả khi mọi **lời ghi riêng lẻ** cập nhật đủ chỉ mục trước khi hoàn tất, một lời **đọc phức hợp** vẫn có thể kết hợp các phiên bản khác nhau nếu nó đọc nhiều bước không được bảo vệ.

Ví dụ truy vấn:

```text
1. Lấy danh sách SKU có category="books".
2. Với từng SKU, lấy bản ghi ở bySku.
3. Lọc tiếp price <= 100.
```

Nếu bước 1 lấy tập ID lúc `t0` còn bước 2 đọc bản ghi đã đổi danh mục/giá lúc `t1`, kết quả có thể không khớp điều kiện của **một thời điểm duy nhất**. Khái niệm thường được gọi là **đọc không nhất quán phiên bản**.

### 10.1. Các mô hình nhất quán đọc

| Mô hình | Hành vi | Khi nào phù hợp |
| --- | --- | --- |
| **Khóa chung cả lượt đọc** | Ghi không chen vào khi một truy vấn phức hợp đọc nhiều chỉ mục | Đơn giản về tính đúng đắn, nhưng có thể giảm thông lượng |
| **Snapshot bất biến** | Truy vấn đọc một phiên bản `S_v` đã cố định | Báo cáo, phân trang và truy vấn đa bước |
| **MVCC / snapshot isolation** | Hệ lưu trữ giữ nhiều phiên bản; transaction đọc một snapshot theo quy tắc | Nhiều truy vấn đồng thời, cần rõ ngữ nghĩa version |
| **Đọc cập nhật dần** | Có thể thấy các chỉ mục ở những phiên bản khác nhau | Chỉ dùng nếu API chấp nhận không đồng nhất tạm thời |

**Snapshot isolation không phải lúc nào cũng tương đương tính tuần tự hóa (serializability)** cho mọi cặp transaction ghi. Nếu cần chống các bất thường giao dịch phức tạp, phải xác định mức cô lập, kiểm soát xung đột ghi và các bất biến tổng thể.

Đối với một API danh sách phân trang, **thứ tự tất định** (chẳng hạn `(price,sku)`) giúp tránh sự mơ hồ khi giá trùng. Nhưng nếu yêu cầu các trang thuộc **cùng một tập dữ liệu**, cần thêm snapshot hoặc chính sách phiên bản. Keyset pagination giúp giảm lệch do offset dịch, **không tự tạo snapshot**.

### 10.2. Khóa khi cập nhật tại chỗ

Nếu dùng một khóa chung bảo vệ `bySku`, `byCategory`, `byPrice` và `byTag`, mọi lời đọc/ghi phải tuân cùng quy tắc:

```text
writer:
    lock
    validate + update all indexes
    commit or rollback
    unlock

reader with multi-index query:
    lock
    read all needed indexes and records
    unlock
```

Cần xác định **mục tiêu về thời gian giữ khóa**. Một truy vấn xuất 100.000 bản ghi mà giữ khóa quá lâu có thể làm các lời ghi phải chờ. Một giải pháp là tạo snapshot dưới khóa rồi duyệt bên ngoài, hoặc dùng MVCC/phiên bản bất biến; đổi lại cần bộ nhớ và chính sách quản lý phiên bản cũ.

### 10.3. Phiên bản dữ liệu và cập nhật đến sai thứ tự

Trong hệ thống phát sự kiện, một chỉ mục phụ có thể được cập nhật qua thông điệp:

```text
v10: A10 price = 120
v11: A10 price = 70
v12: A10 price = 90
```

Nếu sự kiện `v11` được xử lý **sau** `v12` và hệ thống ghi đè vô điều kiện, chỉ mục giá có thể quay về 70 dù bản ghi chính đang là 90.

Có thể gắn **version** hoặc sequence monotonic cho mỗi bản ghi, chỉ áp dụng cập nhật nếu mới hơn phiên bản đã xử lý; đồng thời quản lý tính idempotent để giao lại sự kiện không tạo hai mục giống nhau. Đối với xử lý xóa, cần *tombstone* hoặc metadata tương đương để sự kiện cập nhật cũ không vô tình hồi sinh bản ghi đã xóa.

Cơ chế này không biến các chỉ mục thành nhất quán ngay tức thì, nhưng giúp đạt tính **hội tụ đúng phiên bản** khi sự kiện đến trễ, lặp lại hoặc khác thứ tự.

## 11. Khi các chỉ mục nằm trên nhiều dịch vụ khác nhau

Một tình huống thực tế:

- Bản ghi sản phẩm nằm trong cơ sở dữ liệu chính.
- Chỉ mục tìm kiếm toàn văn nằm ở dịch vụ tìm kiếm.
- Bộ nhớ đệm theo mã nằm trong một cache riêng.
- Bộ đếm thống kê nằm ở hệ phân tích.

Lúc này không thể mặc định một transaction của cơ sở dữ liệu chính sẽ **tự động cập nhật nguyên tử** mọi hệ thống khác.

### 11.1. Chọn ngữ nghĩa nhất quán trước

**Nhất quán mạnh:** sau khi cập nhật thành công, mọi truy vấn thuộc phạm vi cam kết phải thấy cùng trạng thái mới nhất theo hợp đồng. Điều này khó và tốn kém hơn khi có nhiều dịch vụ hoặc nhiều bản sao địa lý.

**Nhất quán cuối cùng (*eventual consistency*):** chỉ mục phụ có thể chậm hơn dữ liệu chính trong một khoảng thời gian, nhưng nếu không có cập nhật mới và quá trình đồng bộ hoạt động, các phiên bản sẽ hội tụ. Đây là một lựa chọn có chủ ý, không phải lỗi nếu API công bố rõ và ứng dụng chịu được.

Một số API có thể chọn hỗn hợp: `getBySku` từ nguồn chính cần nhất quán mạnh, còn gợi ý tìm kiếm có thể trễ vài giây. Cần ghi rõ điều đó trong đặc tả, thay vì mặc định tất cả truy vấn đều trả cùng thời điểm.

### 11.2. Đồng bộ qua outbox hoặc log thay đổi

Một mẫu phổ biến là ghi bản ghi chính và **sự kiện outbox trong cùng transaction của nguồn chính**:

```text
Transaction ở primary database:
    update Product
    append OutboxEvent(productId, version, changedFields)
commit

Background worker:
    read committed outbox event
    update search index / cache / aggregate
    mark progress, retry if needed
```

**Chỉ phần ghi bản ghi + outbox** cùng transaction mới được bảo đảm nguyên tử bởi cơ sở dữ liệu ấy. Cập nhật sang dịch vụ tìm kiếm sau commit vẫn có độ trễ và có thể thất bại; worker phải retry, chống xử lý trùng và theo dõi tiến độ.

Không nên viết theo trình tự “ghi DB xong mới phát sự kiện trực tiếp” mà mặc định an toàn: nếu tiến trình dừng **giữa hai bước**, DB có dữ liệu mới nhưng sự kiện chưa hề được gửi. Outbox giải quyết cửa sổ lỗi này trong phạm vi transaction của nơi lưu, song không tự đảm bảo dịch vụ nhận sự kiện chỉ một lần.

### 11.3. Cơ chế đọc khi chỉ mục phụ chưa bắt kịp

Có thể:

- Trả trạng thái “đang cập nhật”, làm mới kết quả sau.
- Đọc trực tiếp nguồn chính với các truy vấn quan trọng.
- Gắn version/watermark cho chỉ mục, chỉ trả kết quả nếu phiên bản đáp ứng yêu cầu.
- Đưa ra thời gian hội tụ kỳ vọng và đo độ trễ đồng bộ.

Không nên hứa kết quả tức thời nếu kiến trúc dùng đồng bộ bất đồng bộ mà không có cơ chế chờ/đọc tương ứng.

## 12. Kiểm tra, phát hiện và sửa sai lệch giữa các chỉ mục

Dù đã thiết kế đúng, hệ thống thực tế vẫn có thể gặp lỗi logic, lỗi triển khai, hỏng dữ liệu hoặc tiến trình ngừng giữa chừng. Cần có cách **đo tính nhất quán độc lập**.

### 12.1. Kiểm tra bất biến hai chiều

Với `P` là nguồn chính:

```text
expectedCategory = empty map<Category, Set<SKU>>
expectedPrice = empty sorted set<(Price,SKU)>
expectedTag = empty map<Tag, Set<SKU>>

for each (sku, product) in P:
    expectedCategory[product.category].add(sku)
    expectedPrice.add((product.price, sku))
    for tag in product.tags:
        expectedTag[tag].add(sku)

assert expectedCategory == byCategory
assert expectedPrice == byPrice
assert expectedTag == byTag
```

Cách kiểm tra bằng **xây lại kết quả kỳ vọng từ nguồn chính** hữu ích trong kiểm thử và tác vụ bảo trì. Nó phát hiện cả *thiếu* mục lẫn *thừa* mục, trong khi kiểm tra một chiều có thể bỏ qua tham chiếu mồ côi.

Nếu đang có ghi đồng thời, cần chạy kiểm tra trên **cùng một snapshot** hoặc khóa phù hợp. Kiểm tra nguồn chính ở phiên bản mới còn chỉ mục ở phiên bản cũ có thể báo lỗi giả.

### 12.2. Kiểm thử theo chuỗi thao tác

Một mô hình tham chiếu đơn giản có thể chỉ dùng `Map<SKU,Product>` và quét mọi phần tử để trả lời truy vấn. Nó chậm nhưng dễ kiểm tra tính đúng đắn. Sinh các chuỗi thao tác:

1. Thêm A, B, C; truy vấn theo SKU, danh mục và khoảng.
2. Sửa giá xuống rồi lên, với nhiều sản phẩm trùng giá.
3. Đổi danh mục, đổi tập nhãn, sửa chỉ một trường không được đánh chỉ mục.
4. Xóa sản phẩm đầu tiên/cuối cùng trong một nhóm, rồi thêm lại SKU mới theo chính sách.
5. Thử chèn trùng SKU, xóa SKU không tồn tại, giá biên và khoảng rỗng.
6. Sau **mỗi thao tác**, so mọi truy vấn với mô hình tham chiếu và chạy kiểm tra I0–I3.

Dữ liệu thử nên có khóa trùng theo danh mục/giá/nhãn, nhiều lần thay đổi liên tục và tình huống thất bại giữa các bước.

### 12.3. Chèn lỗi có chủ đích (*fault injection*)

Trong môi trường thử nghiệm, mô phỏng lỗi ở từng điểm:

```text
fail after updating primary
fail after removing old price key
fail before inserting new category
fail during transaction commit
fail while building replacement snapshot
```

Kết quả đúng phải theo hợp đồng:

- Nếu giao dịch được báo **thất bại**, hệ thống phải phục hồi hoặc giữ snapshot cũ hợp lệ.
- Nếu giao dịch được báo **thành công**, tất cả chỉ mục thuộc phạm vi giao dịch phải phản ánh bản ghi mới.
- Với cập nhật bất đồng bộ, phải có trạng thái retry và cơ chế hội tụ đã định nghĩa rõ.

Không thử nghiệm lỗi mất điện trên mã copy-on-write trong RAM rồi suy ra khả năng phục hồi bền vững. Kiểm thử crash/recovery cần đúng cơ chế log hoặc transaction của hệ lưu trữ.

### 12.4. Rebuild và backfill chỉ mục

Nếu một chỉ mục phụ bị sai lệch hoặc mới được bổ sung, có thể **xây lại từ nguồn chính**:

1. Chọn một snapshot nguồn nhất quán ở mốc/version `v`.
2. Duyệt nguồn, tạo **chỉ mục mới** độc lập với chỉ mục đang phục vụ.
3. Nếu có cập nhật trong lúc xây, ghi nhận và áp dụng **delta** sau mốc `v` theo thứ tự/phiên bản chính xác.
4. Xác minh chỉ mục mới theo bất biến.
5. Chuyển các truy vấn sang chỉ mục mới bằng cơ chế công bố nguyên tử phù hợp.
6. Chỉ giải phóng chỉ mục cũ khi không còn người đọc cần nó.

Xây lại chỉ mục trên một snapshot tĩnh có thể đơn giản; **xây trong lúc có ghi** đòi hỏi xử lý delta, tombstone và điểm chuyển phiên bản. Nếu chỉ quét nguồn rồi thay chỉ mục mà bỏ qua cập nhật diễn ra giữa hai thời điểm, kết quả mới vẫn có thể thiếu dữ liệu.

## 13. Những sai lầm thường gặp khi duy trì nhiều chỉ mục

**1. Chỉ cập nhật nguồn chính.** Dữ liệu đúng ở `getBySku` nhưng kết quả lọc theo giá/danh mục vẫn dùng khóa cũ.

**2. Chỉ kiểm tra rằng mọi bản ghi có trong chỉ mục.** Chỉ mục có thể giữ thêm khóa không còn sống; phải kiểm tra cả chiều *index → source*.

**3. Dùng khóa giá không phân biệt sản phẩm trùng giá.** Cây set theo `price` có thể bỏ mất các bản ghi khác nhau có cùng giá. Khóa ghép `(price,sku)` hoặc multimap với chính sách trùng rõ ràng là cần thiết.

**4. Sửa đối tượng mutable rồi mới tính khóa cũ.** Không thể xóa đúng khóa giá cũ nếu đã ghi đè `price` trước khi lưu giá trị trước cập nhật.

**5. Coi lock là giải pháp rollback.** Lock ngăn thao tác chen vào trong phạm vi sử dụng đúng, nhưng khi exception xảy ra vẫn phải phục hồi hoặc không công bố trạng thái nửa chừng.

**6. Tạo nhiều bản sao dữ liệu và không định nghĩa nguồn chuẩn.** Khi giá mới và cũ cùng tồn tại ở các bản sao, hệ thống không biết bản nào có thẩm quyền.

**7. Duyệt theo thứ tự tình cờ của hash set.** Chỉ mục danh mục thường trả **một tập** SKU, không hứa thứ tự. Nếu API cần sắp theo giá hoặc tên, phải có chỉ mục thứ tự phù hợp hoặc sắp kết quả.

**8. Giả sử nhiều lần tra cứu trong một lời gọi cùng thuộc một snapshot.** Người ghi có thể chen vào giữa các bước; cần transaction đọc/snapshot hoặc khóa cho phạm vi đọc.

**9. Phân trang bằng offset trong dữ liệu thay đổi nhanh.** Chèn/xóa trước offset gây lặp hoặc bỏ sót. Cursor theo khóa toàn phần giảm một số vấn đề nhưng không thay thế snapshot nếu cần cố định tập kết quả.

**10. Quên cập nhật chỉ mục tổng hợp.** Bộ đếm, tổng doanh thu hoặc số lượng theo trạng thái cũng là dữ liệu dẫn xuất; một thay đổi trường phải cập nhật mọi tổng hợp liên quan.

**11. Xử lý sự kiện ngoài thứ tự mà không xét version.** Một sự kiện cũ đến sau có thể ghi đè dữ liệu mới nếu áp dụng vô điều kiện.

**12. Dùng outbox và mặc định các dịch vụ đồng bộ ngay tức thì.** Outbox giúp không mất sự kiện ở ranh giới commit nguồn chính, nhưng không làm giao dịch trên nhiều dịch vụ trở thành nguyên tử.

**13. Không tính chi phí xây và duy trì chỉ mục.** Một truy vấn nhanh không đủ bù chi phí nhiều lần cập nhật, tăng bộ nhớ, tái xây chỉ mục và đồng bộ.

## 14. Bài tập tự kiểm tra

### Bài 1 — Tính delta đúng khi cập nhật

Có sản phẩm `P1`:

```text
old: category=books, price=90, tags={new, sale}
new: category=books, price=120, tags={sale, gift}
```

**Hỏi:** phải thay những mục nào trong `byCategory`, `byPrice` và `byTag`?

*Đáp án:* danh mục không đổi nên không cần sửa `byCategory`. Cây giá phải xóa `(90,P1)` và thêm `(120,P1)`. Chỉ mục nhãn phải xóa P1 khỏi `new`, thêm vào `gift`, giữ nguyên ở `sale`. Bản ghi chính phải nhận phiên bản mới.

### Bài 2 — Tham chiếu mồ côi

Một sản phẩm `P2` đã bị xóa khỏi `bySku` nhưng `byCategory["tools"]` vẫn chứa `P2`.

**Hỏi:** bất biến nào sai? Vì sao không nên “bỏ qua ID không tìm thấy” rồi coi như hết lỗi?

*Đáp án:* I1 sai ở chiều chỉ mục → nguồn chính. Việc bỏ qua ID chỉ che lỗi khi truy vấn; chỉ mục vẫn chứa dữ liệu thừa và có thể gây sai ở thao tác khác, làm tăng bộ nhớ và gây khó kiểm soát tái sử dụng ID.

### Bài 3 — Tại sao phải giữ khóa ghép?

Ba sản phẩm A, B, C đều có `price=100`. Nếu dùng cây set theo khóa chỉ là 100, có bảo đảm lưu cả ba không?

*Đáp án:* không nếu set không cho khóa trùng. Chọn `(price,sku)` để có ba khóa `(100,A)`, `(100,B)`, `(100,C)`, hoặc multimap có quy tắc lưu nhiều bản ghi cho cùng giá.

### Bài 4 — Thử lỗi giữa chừng

Một hàm cập nhật xóa `(oldPrice,sku)` khỏi cây giá, nhưng bước chèn giá mới thất bại và hàm trả lỗi.

**Hỏi:** chỉ dùng khóa mutex quanh hàm này đã đủ chưa?

*Đáp án:* chưa. Mutex ngăn truy cập đồng thời trong phạm vi đúng, nhưng sau khi mở khóa chỉ mục giá vẫn thiếu bản ghi. Cần rollback, transaction hoặc chuẩn bị snapshot mới trước khi công bố.

### Bài 5 — Chọn cách lưu khi tần suất ghi cao

Cách A xây lại toàn bộ map, chỉ mục danh mục và mảng giá cho mỗi lần sửa; cách B dùng hash map, hash set và cây cân bằng, kèm một giao dịch đồng bộ. Hệ thống có một triệu bản ghi và vài nghìn lần sửa mỗi giây.

*Định hướng:* cách B thường đáng xét vì cập nhật cục bộ giảm chi phí từ `O(n)` sao chép mỗi lần xuống các thao tác phụ thuộc chỉ mục bị ảnh hưởng (kỳ vọng `O(1)` trên map/set, `O(log n)` trên cây). Tuy nhiên, phải tính chi phí giao dịch, lock, bền vững và bộ nhớ thực tế trước khi quyết định.

### Bài 6 — Chỉ mục tìm kiếm cập nhật chậm

Bản ghi chính được sửa thành giá 70 tại version 12; dịch vụ chỉ mục vẫn đang giữ giá 120 ở version 11.

**Hỏi:** có thể gọi hệ thống là nhất quán mạnh cho truy vấn qua chỉ mục này không? Nếu chấp nhận nhất quán cuối cùng thì cần những gì?

*Đáp án:* không thể hứa truy vấn qua chỉ mục phụ thấy ngay version 12. Cần hợp đồng nói rõ độ trễ, đường đồng bộ có retry/idempotency, kiểm soát thứ tự version và quan sát độ trễ hội tụ; hoặc chuyển truy vấn cần chính xác tức thời về nguồn có bảo đảm phù hợp.

### Bài 7 — Đọc nhiều chỉ mục và snapshot

Một truy vấn lấy SKU trong danh mục lúc `t0`, rồi tra giá từng SKU lúc `t1` khi có các cập nhật. Có chắc kết quả là tập sản phẩm đúng ở `t0` hoặc `t1` không?

*Đáp án:* không. Có thể nhận một hỗn hợp không tương ứng với bất kỳ thời điểm nào. Dùng một snapshot nhất quán, transaction đọc thích hợp hoặc khóa cho toàn bộ lời đọc nếu hợp đồng đòi hỏi.

### Bài 8 — Thêm chỉ mục nào là hợp lý?

Ứng dụng có `10^6` bản ghi, tra `sku` nhiều, tìm theo `category` thường xuyên, truy vấn theo `tag` rất hiếm và thay danh sách nhãn liên tục. Có cần chỉ mục `byTag` ngay từ đầu không?

*Định hướng:* cân nhắc lợi ích lọc hiếm so với số lần cập nhật nhãn, bộ nhớ và độ phức tạp nhất quán. Có thể chấp nhận quét hoặc tạo chỉ mục theo nhu cầu/lô nếu tần suất thấp; nếu truy vấn nhãn có giới hạn độ trễ chặt, chỉ mục có thể vẫn cần. Quyết định dựa trên đo tải công việc, không phải quy tắc “mọi trường đều có index”.

## 15. Checklist thiết kế và vận hành

Trước khi đưa thiết kế nhiều chỉ mục vào sử dụng, hãy trả lời:

- **Nguồn chuẩn:** bản ghi nào là nguồn có thẩm quyền? ID có bất biến và không trùng không?
- **Đầu ra truy vấn:** tra cứu chính xác, lọc tập, khoảng, sắp xếp hay tổng hợp? Có cần thứ tự tất định?
- **Khóa phụ:** khóa có trùng không, cần khóa ghép không, cách chuẩn hóa chuỗi/nhãn là gì?
- **Bất biến:** viết được điều kiện hai chiều giữa nguồn chính và từng chỉ mục không?
- **Cập nhật:** với create/update/delete, đã xác định khóa cũ, khóa mới, tập chênh lệch và việc dọn ID mồ côi chưa?
- **Nguyên tử:** khi một bước lỗi, có rollback, transaction hoặc snapshot chưa công bố không? Người đọc có thể quan sát trạng thái nửa chừng không?
- **Đồng thời:** một lời đọc nhiều chỉ mục có dùng cùng phiên bản không? Giới hạn độ trễ khi giữ khóa/snapshot là gì?
- **Phân tán:** chỉ mục ngoài dịch vụ có đồng bộ hay không, có idempotency, retry, version và tombstone không?
- **Chi phí:** cộng cả xây chỉ mục, số thao tác ghi, bộ nhớ, sắp xếp, truy vấn trả nhiều kết quả và tái xây.
- **Kiểm tra:** có đối chiếu với mô hình nguồn chính, chèn lỗi thử nghiệm, audit, rebuild và cách chuyển chỉ mục mới an toàn không?

## Kết luận

**Nhiều chỉ mục giúp mỗi loại truy vấn tìm đúng “đường tắt” đến cùng dữ liệu**, nhưng đồng thời tạo ra một cam kết mới: mọi chỉ mục phải phản ánh đúng vòng đời và phiên bản của những bản ghi mà chúng đại diện. Bảng băm theo ID, tập ID theo danh mục/nhãn và cây cân bằng theo khóa giá chỉ có ích nếu cùng tuân những bất biến hai chiều.

Khi thêm, xóa hoặc sửa, hãy dựa vào **cả trạng thái cũ lẫn mới**, cập nhật các chỉ mục bị ảnh hưởng như **một đơn vị logic**, và chọn cơ chế nguyên tử/nhất quán phù hợp với nơi lưu dữ liệu. Trong RAM có thể dùng khóa và copy-on-write; trong cơ sở dữ liệu có thể dựa vào transaction; giữa nhiều dịch vụ thường cần log sự kiện, version, retry và quy tắc nhất quán cuối cùng được công bố rõ ràng.

Việc lựa chọn cuối cùng phải cân bằng **tốc độ tra cứu, chi phí duy trì, bộ nhớ, tính ổn định danh tính và yêu cầu quan sát nhất quán**. Viết rõ bất biến và kiểm chứng chúng sau mọi thao tác chính là nền tảng để hệ thống có nhiều chỉ mục không chỉ nhanh mà còn **đúng**.
