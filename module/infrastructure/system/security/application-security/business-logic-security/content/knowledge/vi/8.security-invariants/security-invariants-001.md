# Invariant definition — Định nghĩa bất biến bảo mật nghiệp vụ

## 1. Invariant là gì?

**Invariant — bất biến** là một mệnh đề đúng ở mọi trạng thái có thể đạt được của một mô hình hệ thống đã xác định. Khi thiết kế ứng dụng, ta thường bắt đầu bằng **bất biến mong muốn**: điều bắt buộc phải luôn đúng để bảo vệ dữ liệu, tài sản hoặc quyền hạn. Việc viết ra mệnh đề chưa chứng minh triển khai thực tế đã giữ được nó.

Ví dụ:

- Số lượng hàng khả dụng không âm.
- Người tạo đề nghị không phải là người duyệt quyết định đó.
- Tổng tiền đã hoàn cộng phần đang dành để hoàn không vượt ngân sách được phép.
- Một quyền thưởng có danh tính nghiệp vụ cụ thể không được cấp hai lần.

“Bất biến” không có nghĩa các giá trị không thay đổi. Hàng khả dụng có thể giảm từ 10 xuống 6; điều giữ nguyên là quan hệ hoặc giới hạn, chẳng hạn `available >= 0`.

Trong chương **Security Invariants**, mục tiêu là biến yêu cầu bảo vệ nghiệp vụ thành mệnh đề đủ rõ để thực thi và kiểm chứng. Bài học gắn khái niệm đó với quyền theo đối tượng, máy trạng thái, transaction, idempotency và các tình huống tấn công logic.

Sau bài học, bạn có thể:

- Định nghĩa bất biến với đối tượng, miền giá trị, phạm vi và thời điểm quan sát cụ thể.
- Phân biệt bất biến với điều kiện đầu vào, tiền điều kiện và hậu điều kiện.
- Tìm phản ví dụ cho một mệnh đề quá yếu hoặc một triển khai không giữ được mệnh đề.
- Giải thích vì sao mọi đường thay đổi trạng thái đều phải bảo toàn bất biến.
- Chọn cách biểu diễn và kiểm thử mà không nhầm một kiểm tra đơn lẻ với bảo đảm toàn hệ thống.

Định nghĩa theo trạng thái có thể đạt được phù hợp với cách trình bày của Leslie Lamport trong tài liệu TLA+/PlusCal. Bài này dùng ý tưởng đó để phân tích ứng dụng nghiệp vụ, không yêu cầu cài công cụ hình thức. [Nguồn: PlusCal Tutorial — Invariants](https://lamport.azurewebsites.net/tla/tutorial/session6.html#invariants).

## 2. Phải định nghĩa mô hình trước khi nói “luôn đúng”

Một bất biến chỉ có ý nghĩa khi biết hệ thống gồm những gì và những thay đổi nào được phép xảy ra.

### 2.1. Ba thành phần tối thiểu

```text
State S:
  Những dữ liệu có ý nghĩa để quyết định đúng/sai.

Init(S):
  Những trạng thái có thể là điểm bắt đầu.

Next(S, command, S'):
  Những bước chuyển từ trạng thái trước sang trạng thái sau.
```

Ký hiệu `S'` đọc là “trạng thái sau”, không phải đạo hàm. Nếu `I` là mệnh đề cần giữ, mong muốn là:

```text
Với mọi trạng thái S có thể đạt được:
  I(S) = true
```

“Có thể đạt được” được xác định từ trạng thái ban đầu và các bước của mô hình. Không được định nghĩa nó thành “những trạng thái đã thỏa I” rồi dùng chính định nghĩa đó để kết luận I luôn đúng; cách làm ấy che mất lỗi cần tìm.

### 2.2. Phạm vi quan sát là một phần của đặc tả

Trong ứng dụng dùng cơ sở dữ liệu, có thể chọn trạng thái nghiệp vụ sau mỗi transaction đã commit làm ranh giới quan sát. Một thao tác nội bộ có nhiều câu lệnh, nhưng các thay đổi liên quan cần xuất hiện như một đơn vị nhất quán đối với bên quan sát được quy định.

Điều này không cho phép tạo tác dụng bên ngoài trong lúc dữ liệu còn sai rồi trông chờ rollback sửa lại. Một email, lệnh giao hàng hoặc lần hoàn tiền đã phát ra ngoài có thể là phần trạng thái quan sát được mà transaction cục bộ không thu hồi được.

Cần ghi rõ:

- Bất biến áp dụng cho một đối tượng, một tenant, một tập đối tượng hay toàn hệ thống?
- Nó được yêu cầu sau mỗi phương thức, mỗi transaction hay mỗi bước của giao thức phân tán?
- Dữ liệu cache hoặc bản sao đọc là nguồn sự thật hay chỉ là hình chiếu có thể trễ?
- Actor, job, nhập dữ liệu, migration và thao tác quản trị nào có thể thay đổi trạng thái?

### 2.3. Trạng thái có thể bao gồm bằng chứng hoặc lịch sử

Mệnh đề “mọi quyết định duyệt được chấp nhận đều do người khác người lập thực hiện” cần dữ liệu về người lập và người duyệt của quyết định đó. Chỉ nhìn trường trạng thái hiện tại của đề nghị có thể không đủ.

Một yêu cầu về lịch sử thao tác có thể được kiểm tra bằng cách lưu bằng chứng cần thiết trong mô hình trạng thái. Không được suy ra lịch sử đúng chỉ vì bản ghi cuối cùng có hình dạng hợp lệ.

## 3. Phân biệt invariant với các khái niệm gần nhau

| Khái niệm | Khi nào cần đúng? | Ví dụ giữ hàng |
| --- | --- | --- |
| Điều kiện đầu vào | Khi tiếp nhận lệnh theo hợp đồng | `quantity` là số nguyên dương trong giới hạn |
| Tiền điều kiện | Trước một thao tác cụ thể | Còn ít nhất `quantity` hàng để giữ |
| Hậu điều kiện | Sau thao tác thành công | Hàng khả dụng giảm và hàng đang giữ tăng cùng lượng |
| Bất biến | Mọi trạng thái quan sát được thuộc mô hình | Các lượng không âm và tổng được bảo toàn |
| Yêu cầu tiến triển | Trên quá trình chạy, với điều kiện đã định nghĩa | Công việc đã nhận cuối cùng được xử lý hoặc giải quyết |

Các nhóm không hoàn toàn loại trừ nhau. `quantity > 0` là điều kiện của một request; nếu mô hình yêu cầu mọi reservation đã lưu đều có lượng dương thì mệnh đề lượng dương cho toàn bộ reservation cũng là một bất biến trạng thái.

### 3.1. Một thao tác có thể thành công đúng mà toàn hệ thống vẫn sai

Hàm giữ hàng có hậu điều kiện “tạo một reservation với lượng yêu cầu”. Nếu thiếu điều kiện về tổng, hai lần gọi có thể cùng tạo reservation vượt nguồn hàng. Hậu điều kiện của từng lần gọi chưa diễn đạt đủ điều cần bảo vệ.

Ngược lại, kiểm tra bất biến sau thao tác không cho biết thao tác có thực hiện đúng mục đích hay không. Một hàm không làm gì có thể giữ `available >= 0`, nhưng không đáp ứng yêu cầu giữ hàng hợp lệ.

### 3.2. Safety và liveness bổ sung cho nhau

Các bất biến bảo mật trong bài chủ yếu diễn đạt **safety**: trạng thái xấu không xuất hiện, như không bán vượt kho hoặc không tự duyệt.

**Liveness** quan tâm đến tiến triển, như công việc đang chờ cuối cùng được giải quyết khi các điều kiện vận hành cần thiết được đáp ứng. Giữ tài nguyên mãi mãi có thể không phá một công thức tổng, nhưng làm người khác không sử dụng được hệ thống.

Một quy trình từ chối mọi lệnh có thể giữ nhiều bất biến nhưng không phục vụ được nghiệp vụ. Cần đồng thời kiểm thử những thao tác được phép thực sự thành công; không biến định nghĩa invariant thành lý do chặn toàn bộ hệ thống.

### 3.3. Bất biến không phải tính bất biến của đối tượng Java

Một record hoặc đối tượng không cho sửa thuộc tính có thể giúp tránh thay đổi dở dang trong bộ nhớ. Nó vẫn có thể biểu diễn trạng thái sai nếu constructor nhận dữ liệu không hợp lệ.

Ngược lại, một aggregate có trạng thái thay đổi vẫn giữ invariant nếu mọi phép chuyển hợp lệ đều bảo toàn điều kiện. “Immutable object” và “invariant của nghiệp vụ” giải quyết những vấn đề liên quan nhưng khác nhau.

## 4. Cách viết một bất biến đủ rõ

Một phát biểu tốt cần chỉ ra ít nhất đối tượng, điều kiện, đơn vị, phạm vi và ranh giới áp dụng.

### 4.1. Chuyển câu mơ hồ thành mệnh đề kiểm tra được

| Câu còn mơ hồ | Cách cụ thể hóa theo một chính sách giả định |
| --- | --- |
| Không được hoàn tiền quá mức | Với mỗi thanh toán và loại tiền, tổng đã hoàn cộng đang dành không vượt ngân sách hoàn đã xác định |
| Không được tự duyệt | Với mỗi quyết định duyệt được chấp nhận, con người duyệt khác con người lập theo định danh đáng tin |
| Mã ưu đãi dùng một lần | Với mỗi cặp quyền ưu đãi–chủ thể đủ điều kiện, số lần tiêu quyền thành công không vượt 1 |
| Đơn phải hợp lệ trước khi giao | Mỗi ý định giao được tiếp nhận phải có căn cứ cấp quyền, đúng nội dung và không vượt lượng còn được phép |

Ví dụ “một lần” cần đơn vị định danh: một tài khoản, một con người, một đơn hay một chiến dịch? Nếu chính sách chỉ giới hạn tài khoản, không được mô tả như thể nó đã chứng minh giới hạn theo con người.

### 4.2. Viết rõ điều kiện kích hoạt

Đề nghị `DRAFT` chưa cần có người duyệt. Bất biến có điều kiện có thể là:

```text
Với mọi đề nghị r:
  nếu r đang ở trạng thái yêu cầu phê duyệt còn hiệu lực
  thì tồn tại bằng chứng duyệt hợp lệ gắn đúng phiên bản nội dung.
```

Nếu không có đề nghị nào đạt trạng thái đó, mệnh đề vẫn đúng nhưng chưa chứng minh luồng duyệt có thể chạy. Đây là lý do phải kiểm tra cả điều kiện được phép và yêu cầu tiến triển.

### 4.3. Dùng đúng nguồn và thời điểm của sự thật

Giá, chủ sở hữu, tenant, danh tính actor và quyền không được lấy từ dữ liệu client tự khai nếu chúng là căn cứ bảo vệ. Một mệnh đề so sánh hai trường đều do cùng người gọi tùy ý sửa có thể luôn đúng mà không bảo vệ gì.

Với quyết định lịch sử, cần phân biệt quyền tại thời điểm quyết định với quyền hiện tại. Việc người duyệt đổi vai trò sau đó không tự chứng minh phê duyệt cũ là sai. Nếu chính sách yêu cầu đóng băng những quyết định chưa thực thi khi thu hồi quyền, hãy mô tả thêm điều kiện đó riêng.

OWASP Business Logic Security khuyến nghị ghi rõ các bất biến và xác định nơi thực thi chúng. Bất biến cần đi cùng nguồn dữ liệu và cơ chế bảo vệ tại thao tác, không chỉ xuất hiện trong tài liệu. [Nguồn: OWASP Business Logic Security](https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html).

## 5. Ví dụ xuyên suốt: ngân sách tồn kho của một SKU

### 5.1. Chọn giả định của mô hình

Giả sử một SKU trong một tenant có 10 đơn vị ban đầu. Trong phạm vi ví dụ không có nhập thêm, mất hàng, điều chỉnh hoặc hàng trả lại. Mỗi reservation được xác nhận hoặc hủy toàn bộ; xử lý từng phần cần mở rộng mô hình.

Đặt:

- `C`: lượng ban đầu, bằng 10 và không đổi trong ví dụ.
- `A`: lượng khả dụng.
- `R`: lượng đang dành cho reservation chưa kết thúc rõ ràng.
- `F`: lượng đã được ghi nhận sử dụng tại điểm cam kết fulfillment đã định nghĩa.

Các lượng cùng đơn vị sản phẩm, cùng SKU và cùng tenant. Không cộng số lượng khác loại hàng hoặc khác phạm vi.

### 5.2. Một tập bất biến thay vì một công thức duy nhất

```text
I1 — Miền giá trị:
  C, A, R, F là số nguyên không âm.

I2 — Bảo toàn ngân sách:
  A + R + F = C.

I3 — Khớp chi tiết:
  R = tổng quantity của những reservation đang giữ ngân sách
      thuộc đúng tenant và SKU.

I4 — Liên kết:
  mỗi reservation gắn với đúng ngân sách được phép;
  quantity của nó dương và không bị gán tùy ý sang tenant khác.
```

Những trạng thái còn có thể thực hiện hoặc chưa rõ kết quả phải nằm trong tập “đang giữ ngân sách” theo mô hình. Chỉ cộng `ACTIVE` mà bỏ trạng thái đang thực thi sẽ làm số còn lại trông lớn hơn thực tế.

Tập bất biến có thể cần thêm điều kiện về lượng đã xác nhận, định danh ý định và hiệu ứng ngoài. Bốn điều trên đủ để bắt đầu phân tích ví dụ, chưa phải bảo đảm đầy đủ cho một hệ thống kho phân tán.

### 5.3. Các giá trị thay đổi nhưng quan hệ được giữ

| Bước | A | R | F | A + R + F |
| --- | --- | --- | --- | --- |
| Khởi tạo | 10 | 0 | 0 | 10 |
| Giữ 4 | 6 | 4 | 0 | 10 |
| Xác nhận toàn bộ reservation 4 | 6 | 0 | 4 | 10 |
| Giữ thêm 2 | 4 | 2 | 4 | 10 |
| Hủy reservation 2 an toàn | 6 | 0 | 4 | 10 |

Mỗi bước còn phải cập nhật chi tiết reservation để `I3` đúng tại ranh giới quan sát. Giữ được tổng trên một bản ghi nhưng quên cập nhật chi tiết vẫn là vi phạm tập bất biến.

Nếu có nhập kho hoặc trả hàng, không tiếp tục dùng giả định “C cố định” một cách ngầm định. Cần bổ sung nguồn vào/ra hoặc ledger điều chỉnh, quyền thực hiện và công thức bảo toàn tương ứng.

### 5.4. Phản ví dụ cho một tập điều kiện quá yếu

Giả sử hai request cùng đọc `A = 10`, mỗi request muốn giữ 7. Triển khai sai tính toán trên bản sao rồi ghi giá trị tuyệt đối:

```text
Request X đọc A=10, R=0 và tạo reservation 7.
Request Y cũng đọc A=10, R=0 và tạo reservation 7.

X ghi A=3, R=7.
Y ghi đè A=3, R=7 theo bản sao cũ.
```

Bộ đếm cuối vẫn không âm và `A + R + F = 10`. Nhưng hai reservation đã nhận tổng 14, trong khi `R = 7`; `I3` bị phá.

Kết luận không phải công thức bảo toàn sai. Nó đúng nhưng chưa đủ để diễn đạt toàn bộ mục tiêu. Cần cả liên kết với các cam kết chi tiết và cơ chế cạnh tranh bảo vệ việc ghi.

## 6. Vì sao mọi bước chuyển đều phải bảo toàn bất biến?

### 6.1. Hai câu hỏi nền tảng

Một cách đủ để chứng minh mệnh đề `I` được bảo toàn là:

```text
Khởi đầu:
  Init(S) => I(S)

Bảo toàn qua bước chuyển:
  I(S) AND Next(S, command, S') => I(S')
```

Từ điểm bắt đầu đúng, mỗi bước đều giữ đúng thì mọi trạng thái đạt được qua các bước đó cũng đúng. Tuy nhiên, không phải mọi invariant mong muốn đều tự đủ mạnh cho chứng minh quy nạp; có thể cần một mệnh đề mạnh hơn `J` được bảo toàn và suy ra `I`. [Nguồn: Leslie Lamport — Inductive Invariance](https://lamport.azurewebsites.net/tla/inductive-invariant.pdf).

Trong phát triển thông thường, cách suy nghĩ này dẫn đến hai việc cụ thể: kiểm tra dữ liệu ban đầu và liệt kê đầy đủ các đường ghi có thể làm thay đổi điều kiện.

### 6.2. Minh họa phép giữ hàng

Với lượng `q`, chọn tiền điều kiện `q > 0` và `A >= q`. Hậu trạng thái của giữ hàng thành công:

```text
A' = A - q
R' = R + q
F' = F
C' = C
```

Khi đó:

```text
A' + R' + F'
  = (A - q) + (R + q) + F
  = A + R + F
  = C
```

Tiền điều kiện giữ `A'` không âm. Để khớp chi tiết, cùng bước còn phải tạo đúng một reservation lượng `q` trong phạm vi tương ứng. Phép biến đổi trên giấy chưa chứng minh được concurrency, quyền người gọi hoặc hiệu ứng ngoài.

### 6.3. Kể cả lỗi và đường quản trị cũng là một phần của mô hình

Các bước cần xem xét gồm tạo, sửa, hủy, xác nhận, retry, worker, import, migration và thao tác vận hành. Nếu một đường ghi trực tiếp bỏ qua kiểm soát, nó vẫn có thể đưa hệ thống tới trạng thái sai.

Với lệnh bị từ chối trước thay đổi, mong muốn thường là trạng thái nghiệp vụ không đổi. Audit từ chối có thể tăng thêm, nên “không đổi” cần nói rõ là phần trạng thái nào; không được viết công thức bao trùm cả log rồi coi việc ghi log là một vi phạm.

Nếu dữ liệu hiện có đã sai, một hàm mới giữ bất biến khi đầu vào đúng không tự chữa được trạng thái ban đầu. Cần kế hoạch kiểm tra, đối soát và sửa dữ liệu có bằng chứng trước khi tuyên bố toàn bộ trạng thái đã đáp ứng điều kiện.

## 7. Ví dụ Java: bảo vệ bất biến cục bộ bằng kiểu giá trị

Đoạn mã sau biểu diễn phần số học `I1` và `I2`. Nó không quản lý reservation chi tiết, danh tính actor hoặc đồng bộ cơ sở dữ liệu.

```java
public record InventoryBudget(
        long initial,
        long available,
        long reserved,
        long fulfilled) {

    public InventoryBudget {
        if (initial < 0 || available < 0
                || reserved < 0 || fulfilled < 0) {
            throw new IllegalArgumentException("NEGATIVE_QUANTITY");
        }

        long accounted = Math.addExact(
                Math.addExact(available, reserved), fulfilled);

        if (accounted != initial) {
            throw new IllegalArgumentException("UNBALANCED_INVENTORY");
        }
    }

    public InventoryBudget reserve(long quantity) {
        if (quantity <= 0 || quantity > available) {
            throw new IllegalArgumentException("INSUFFICIENT_INVENTORY");
        }

        return new InventoryBudget(
                initial,
                available - quantity,
                Math.addExact(reserved, quantity),
                fulfilled);
    }
}
```

`new InventoryBudget(10, 10, 0, 0).reserve(4)` tạo giá trị có `available = 6`, `reserved = 4`. Dành thêm 7 từ giá trị đó bị từ chối. `new InventoryBudget(10, 3, 6, 0)` cũng bị từ chối vì tổng chỉ là 9.

Constructor kiểm tra trạng thái và phương thức diễn đạt một phép chuyển có tiền điều kiện rõ. `Math.addExact` phát hiện tràn số thay vì để phép cộng vòng qua miền `long`; lớp ứng dụng cần xử lý lỗi trước khi lưu hoặc phát tác dụng.

Không bind request trực tiếp vào kiểu miền để cho client tự khai lượng ban đầu hay lượng đã thực hiện. Dữ liệu đó phải đến từ nguồn nội bộ đáng tin.

Hai bản sao Java có thể cùng vượt qua kiểm tra cục bộ trên dữ liệu cũ. Vì thế, đoạn mã không chứng minh `I3` hoặc an toàn trước hai tiến trình. Không nên mô tả nó như toàn bộ kiểm soát giữ hàng.

## 8. Ràng buộc dữ liệu và tính nguyên tử

### 8.1. Những bất biến có thể diễn đạt trên một dòng

Ví dụ schema PostgreSQL cho ngân sách đang xét:

```sql
CREATE TABLE inventory_budget (
    tenant_id UUID NOT NULL,
    sku_id UUID NOT NULL,
    initial_quantity BIGINT NOT NULL,
    available_quantity BIGINT NOT NULL,
    reserved_quantity BIGINT NOT NULL,
    fulfilled_quantity BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, sku_id),
    CONSTRAINT ck_non_negative CHECK (
        initial_quantity >= 0
        AND available_quantity >= 0
        AND reserved_quantity >= 0
        AND fulfilled_quantity >= 0
    ),
    CONSTRAINT ck_inventory_conservation CHECK (
        initial_quantity = available_quantity
                         + reserved_quantity
                         + fulfilled_quantity
    )
);
```

`NOT NULL` là một phần của đặc tả, không phải chi tiết trang trí. Trong PostgreSQL, `CHECK` không tự chặn giá trị null chỉ vì biểu thức có phép so sánh. Đồng thời, `CHECK` thông thường không bảo vệ điều kiện tổng tham chiếu các dòng khác; cần công cụ thích hợp cho từng dạng quan hệ. [Nguồn: PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).

Schema trên chưa bảo đảm bộ đếm khớp reservation. Khóa ngoại có thể bảo vệ liên kết tồn tại và đúng tenant khi thiết kế phù hợp; nó không tự chứng minh tổng reservation bằng `reserved_quantity`.

### 8.2. Kiểm tra và ghi phải cùng bảo vệ một quyết định

Một cập nhật có điều kiện cho phần ngân sách:

```sql
UPDATE inventory_budget
SET available_quantity = available_quantity - :quantity,
    reserved_quantity = reserved_quantity + :quantity
WHERE tenant_id = :trusted_tenant_id
  AND sku_id = :verified_sku_id
  AND :quantity > 0
  AND available_quantity >= :quantity;
```

Chỉ tiếp tục nếu `affectedRows = 1`. Cần chèn reservation và ghi những dữ liệu bắt buộc trong cùng transaction; nếu bước sau thất bại, rollback phần ngân sách đã chuyển.

Các phương án khóa, cập nhật có điều kiện, optimistic locking hoặc mức cô lập phù hợp phải được chọn theo bất biến cần giữ. Chỉ thêm một annotation transaction không tự loại bỏ mọi lịch chạy sai.

### 8.3. Phân biệt ranh giới nghiệp vụ với lúc kiểm tra constraint

Một invariant liên kết nhiều dòng có thể được yêu cầu ở trạng thái commit, trong khi phần cài đặt phải qua nhiều câu lệnh. Cần kiểm soát cách những câu lệnh đó được nhóm và cách các bên khác quan sát.

Không suy ra rằng mọi constraint đều được hoãn đến commit. Loại ràng buộc và cấu hình cơ sở dữ liệu quyết định thời điểm kiểm tra. Trong ví dụ, cập nhật đồng thời hai bộ đếm bằng một câu lệnh giữ công thức trên dòng; việc khớp reservation cần cơ chế nhất quán bổ sung.

Đối soát cũng cần một ảnh chụp nhất quán. Đọc bộ đếm ở một thời điểm rồi đọc tổng chi tiết ở thời điểm khác có thể báo chênh lệch dù từng trạng thái commit đều đúng. Ngược lại, đọc từ cache trễ không đủ để kết luận nguồn dữ liệu chính đã vi phạm.

## 9. Bất biến bảo mật còn liên quan đến actor, trạng thái và danh tính thao tác

### 9.1. Quyền gọi là điều kiện trên một bước; lịch sử đúng cần bằng chứng

Quy tắc “actor phải được phép duyệt đối tượng này” được đánh giá khi tiếp nhận hoặc thực hiện một bước. Để diễn đạt mục tiêu tương ứng thành mệnh đề về trạng thái, có thể đưa các quyết định được chấp nhận và bằng chứng của chúng vào mô hình:

```text
Với mọi quyết định duyệt đã được chấp nhận:
  có căn cứ quyền áp dụng cho đúng actor, hành động,
  tenant và đối tượng theo chính sách tại thời điểm quyết định;
  người duyệt không phải người lập nếu chính sách yêu cầu;
  nội dung được thực hiện khớp nội dung đã được chấp nhận.
```

Không chỉ kiểm tra `approvedBy IS NOT NULL`. Một giá trị không rỗng không chứng minh người đó có quyền hoặc quá trình không bỏ bước.

Bằng chứng cũng phải được tạo và bảo vệ bởi cơ chế đáng tin. Nếu client được tự điền toàn bộ dữ liệu “đã duyệt”, việc bản ghi đủ trường không tạo ra bảo đảm bảo mật.

### 9.2. Trạng thái cuối không chứng minh thứ tự đã đúng

Một bản ghi `PAID` hoặc `APPROVED` có thể có đầy đủ trường nhưng được tạo từ một bước chuyển trái phép. Enum giới hạn tên trạng thái, không tự giới hạn đồ thị chuyển trạng thái.

Cần mô hình thao tác có điều kiện, chẳng hạn chỉ `SUBMITTED` mới được duyệt, và bằng chứng cần thiết để xác minh nguồn của quyết định. Khi cho phép sửa nội dung sau duyệt, phải mô hình việc vô hiệu hóa hoặc thay thế quyết định theo chính sách.

### 9.3. At-most-once không đồng nghĩa mọi request chỉ được gửi một lần

Một bất biến có thể là:

```text
Với mỗi ý định nghiệp vụ được định danh:
  số tác dụng nghiệp vụ được chấp nhận không vượt 1.
```

Client có thể retry nhiều lần và nhận lại kết quả mà không vi phạm. Định danh ý định, phạm vi khóa và tác dụng cần được định nghĩa; không coi mọi request có khóa mới là một quyền mới được cấp.

Điều kiện “không quá một lần” là một giới hạn an toàn. Muốn “cuối cùng thực hiện được một lần” còn cần khả năng tiến triển và phục hồi. Việc nhà cung cấp có thể nhận nhiều lần gửi lệnh nhưng chống hiệu ứng trùng khác với tuyên bố mạng chỉ giao một thông điệp duy nhất.

### 9.4. Dữ liệu không đổi chưa chứng minh thao tác đọc an toàn

Một endpoint có thể trả dữ liệu của tenant khác mà không ghi database. Nếu mô hình chỉ gồm các bảng dữ liệu và kiểm tra tổng bộ đếm, nó sẽ không thấy vi phạm tiết lộ.

Để phân tích mục tiêu đó, cần đưa kết quả quan sát, người nhận và quan hệ được phép vào mô hình hành vi hoặc trạng thái mở rộng. Kiểm thử cần kiểm tra nội dung phản hồi và quyền đọc, không chỉ xác nhận dữ liệu chưa bị sửa.

## 10. Thời gian và hệ thống phân tán làm thay đổi điều phải mô hình hóa

### 10.1. Thời gian không tự bảo toàn điều kiện

Một dòng `expiresAt` không tự khiến reservation ngừng tồn tại hoặc trả hàng về kho. Nếu chính sách cho hết hạn, cần bước chuyển và chủ thể thực hiện bước đó.

“Reservation hết hạn cuối cùng được giải quyết” là yêu cầu tiến triển, cần những giả định như worker có cơ hội chạy và các phụ thuộc cần thiết có thể phục hồi. Nếu có yêu cầu thời gian cụ thể, phải mô hình đồng hồ, ngưỡng và ranh giới quan sát tương ứng; không chỉ thêm timestamp rồi coi đã bảo đảm.

Đối với quyền truy cập có thời hạn, kiểm tra hiệu lực ở thời điểm quyết định theo hợp đồng. Nếu muốn ngăn thao tác sau một lần thu hồi, cần quy định thời điểm thu hồi có hiệu lực và cách phối hợp với công việc đang chạy.

### 10.2. Kết quả bên ngoài chưa rõ phải là một trạng thái có chủ đích

Giả sử hệ thống đã gửi lệnh fulfillment nhưng mất phản hồi. Bên ngoài có thể đã xử lý. Nếu nội bộ tự hủy reservation và trả hàng về khả dụng, người khác có thể dùng lại tài nguyên đã được cam kết.

Vì vậy, mô hình cần giữ phần đang thực thi/chưa rõ trong ngân sách thích hợp, liên kết với ý định bền vững và có đường tra cứu hoặc đối soát. Chỉ giải phóng khi có căn cứ phù hợp rằng tác dụng không còn có thể xảy ra, hoặc đi qua một luồng bù được định nghĩa.

Transaction trong một database không tự bao trùm tác dụng bên ngoài. Bảo đảm chống trùng ở bên nhận, định danh ổn định và khả năng phục hồi là những phần phải được đưa vào giả định hoặc thiết kế.

### 10.3. Phân biệt trạng thái nguồn với hình chiếu có thể trễ

Một màn hình báo cáo có thể chậm cập nhật lượng hàng đang giữ. Có thể chấp nhận điều đó nếu nó không phải nguồn cấp quyền giữ hàng và độ trễ phù hợp hợp đồng.

Ngược lại, không được dùng cùng lý do “eventual consistency” để cho hai nơi cấp cùng một nguồn hàng vượt giới hạn cứng rồi hứa đối soát sau. Nếu cần phân tán cấp quyền, phải có thiết kế phân bổ ngân sách hoặc giao thức phối hợp giữ được mục tiêu an toàn đã chọn.

Một quan hệ chỉ hội tụ trở lại sau sự cố không phải bất biến đúng trong toàn bộ khoảng sai lệch của mô hình đó. Có thể đặc tả quan hệ hội tụ riêng và giữ một bất biến mạnh hơn trên nguồn quyền có thẩm quyền.

## 11. Kiểm chứng bằng phản ví dụ và các tầng kiểm thử

### 11.1. Một phản ví dụ đủ bác bỏ mệnh đề được cho là luôn đúng

Nếu tồn tại một trạng thái đạt được làm `I` sai, cần tìm chuỗi ngắn dẫn tới nó:

```text
Trạng thái ban đầu
  → lệnh hoặc bước 1
  → bước 2
  → ...
  → trạng thái I(S) = false
```

Chuỗi đó có thể cho thấy code sai, giả định môi trường sai hoặc phát biểu bất biến chưa đúng chính sách. Đừng sửa một test để bỏ trạng thái khó mà không giải thích vì sao trạng thái đó thật sự không thể xảy ra.

### 11.2. Ma trận kiểm thử cho mô hình tồn kho

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Khởi tạo 10 khả dụng, các lượng khác bằng 0 | Miền giá trị và tổng đúng |
| Khởi tạo tổng thành phần khác lượng ban đầu | Bị từ chối hoặc được phát hiện trước khi dùng như trạng thái đúng |
| Giữ một lượng hợp lệ | Bộ đếm và reservation chi tiết cùng thay đổi đúng |
| Giữ đúng lượng còn lại | Đạt biên hợp lệ, không bị từ chối do dùng sai phép so sánh |
| Giữ vượt lượng còn lại | Không thay đổi ngân sách hoặc tạo reservation thành công |
| Giữ lượng 0, âm hoặc quá giới hạn kiểu | Bị chặn theo hợp đồng; không trông chờ công thức tổng tự bắt mọi lỗi |
| Hai request cùng tranh lượng cuối | Không có tổng reservation vượt ngân sách |
| Ghi chi tiết thất bại sau cập nhật bộ đếm | Toàn bộ thay đổi liên quan rollback |
| Xác nhận hoặc hủy được gửi lại | Không tiêu hoặc trả cùng lượng hai lần |
| Hủy cạnh tranh với xác nhận | Chỉ một kết quả hợp lệ thắng; các lượng vẫn khớp chi tiết |
| Thay tenant/SKU bằng đối tượng ngoài quyền | Không tác động nguồn khác; không lộ dữ liệu ngoài phạm vi |
| Tác dụng ngoài đã xảy ra nhưng phản hồi mất | Không giải phóng tùy tiện phần đang dành |
| Import, migration hoặc công cụ vận hành ghi dữ liệu | Cùng đặc tả được áp dụng hoặc có quy trình chuyển đổi rõ ràng |
| Mọi request bị chặn để giữ số liệu | Phát hiện thiếu chức năng qua test thao tác hợp lệ và yêu cầu tiến triển |

### 11.3. Mỗi phương pháp chứng minh được những điều khác nhau

**Kiểm thử đơn vị** phù hợp với constructor, phép chuyển số học, điều kiện actor và máy trạng thái trên dữ liệu được kiểm soát.

**Kiểm thử tích hợp** xác minh ràng buộc, transaction, rollback và cạnh tranh ở cơ sở dữ liệu thật. Cần kết nối/giao dịch độc lập và điểm đồng bộ; một mock luôn thực hiện tuần tự không chứng minh lịch chạy cạnh tranh an toàn.

**Kiểm thử sinh dữ liệu hoặc chuỗi thao tác** có thể tạo nhiều thứ tự giữ, hủy, xác nhận, retry rồi kiểm tra bất biến sau mỗi bước quan sát. Khi thất bại, giảm chuỗi về phản ví dụ nhỏ để hiểu nguyên nhân.

**Model checking hoặc chứng minh hình thức** có thể phân tích mô hình có các giả định xác định. Kết quả trên một mô hình hữu hạn chưa tự chứng minh mọi triển khai Java, cấu hình database hoặc hệ thống ngoài đều tương đương với mô hình.

Một số test vượt qua không chứng minh mệnh đề đúng với mọi trạng thái và mọi lịch chạy. Tuy nhiên, phản ví dụ tìm được là bằng chứng cụ thể cần xử lý. Các ví dụ kiểm thử trong bài là đặc tả học tập, chưa phải báo cáo chạy thử một triển khai.

## 12. Mẫu đặc tả invariant và những sai lầm cần tránh

### 12.1. Mẫu có thể dùng cho một bất biến mới

```text
Mã và mục tiêu:
  INV-... bảo vệ tài sản, quyền hoặc quyết định nào?

Mô hình và phạm vi:
  Đối tượng, tenant, đơn vị, loại tiền hoặc đơn vị số lượng nào?
  Những biến, quan hệ và bằng chứng nào thuộc trạng thái?

Mệnh đề:
  Phát biểu tự nhiên và biểu thức có thể kiểm tra.
  Nếu có điều kiện kích hoạt, nêu rõ điều kiện đó.

Ranh giới quan sát:
  Sau phương thức, transaction hay bước giao thức nào?
  Nguồn sự thật và hình chiếu có độ trễ được phân biệt ra sao?

Khởi đầu và giả định:
  Dữ liệu ban đầu được xác minh thế nào?
  Những khả năng môi trường hoặc hệ thống ngoài nào đang được giả định?

Các bước phải bảo toàn:
  Tạo, sửa, hủy, xác nhận, retry, worker, import và quản trị.

Cơ chế thực thi:
  Điểm quyết định, quyền theo đối tượng, transaction,
  ràng buộc, khóa/phiên bản và idempotency liên quan.

Phản ví dụ và kiểm thử:
  Chuỗi nào có thể làm mệnh đề sai?
  Trường hợp được phép, biên, cạnh tranh và lỗi được kiểm tra thế nào?

Quan sát và xử lý vi phạm:
  Dữ liệu nào phát hiện được lệch?
  Ai được đối soát/khắc phục và bằng chứng nào phải được giữ?
```

### 12.2. Những phát biểu dễ gây hiểu nhầm

| Phát biểu | Vấn đề cần sửa |
| --- | --- |
| “Đã validate request nên invariant được giữ” | Request đúng chưa chứng minh quan hệ dữ liệu, thứ tự và cạnh tranh đúng |
| “Có CHECK nên mọi quy tắc đều được bảo vệ” | Cần biết phạm vi, null, quan hệ nhiều dòng và thời điểm kiểm tra |
| “Dùng transaction là đủ” | Cần chọn cách đồng bộ và ràng buộc phù hợp từng bất biến |
| “Trạng thái cuối đẹp nên quy trình đúng” | Có thể đã bỏ bước hoặc tạo tác dụng trái phép trước đó |
| “Sau đó sửa lại là vẫn luôn đúng” | Một vi phạm đã quan sát được không biến mất khỏi lịch sử vì có bù |
| “Số dư/tồn kho luôn không âm trong mọi sản phẩm” | Sản phẩm có thấu chi hoặc backorder cần mô hình và giới hạn khác |
| “Test pass nghĩa là đã chứng minh mọi trường hợp” | Phải nêu phạm vi dữ liệu, lịch chạy, mô hình và giả định đã kiểm tra |

Nếu nghiệp vụ thay đổi, có thể cần sửa đặc tả và chuyển dữ liệu theo chính sách mới. Điều đó khác với âm thầm bỏ một điều kiện khi gặp lỗi. Một ngoại lệ cũng phải được biểu diễn trong mô hình, không trở thành đường ghi không có quy tắc.

Định nghĩa invariant rõ ràng tạo một tiêu chí chung cho thiết kế, triển khai và kiểm thử: **điều gì phải đúng, trên phạm vi nào, ở những trạng thái quan sát nào và nhờ những bước bảo toàn nào**. Khi tiêu chí đó có dữ liệu và bằng chứng tương ứng, nhóm phát triển mới có thể đánh giá một thay đổi đã giữ được an toàn nghiệp vụ đến đâu.
