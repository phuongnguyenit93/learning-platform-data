# Khóa ý định và phối hợp nhiều cấp độ khóa

Trong cơ sở dữ liệu, một giao dịch có thể cần khóa cả bảng, một trang dữ liệu hoặc chỉ một dòng. Khóa ở cấp lớn giúp quản lý đơn giản nhưng làm giảm khả năng truy cập đồng thời. Khóa ở cấp nhỏ cho phép nhiều giao dịch làm việc song song hơn, nhưng hệ quản trị phải theo dõi nhiều khóa và vẫn cần bảo vệ những giao dịch đang yêu cầu khóa ở cấp lớn.

**Khóa ý định (intention lock)** giải quyết phần phối hợp này. Nó ghi nhận rằng một giao dịch dự định lấy khóa trên các nút con của một nút trong cây dữ liệu. Nhờ dấu hiệu đó, hệ quản trị có thể kiểm tra xung đột ngay tại cấp cha mà không phải duyệt tất cả các dòng bên dưới.

## 1. Vì sao cần khóa ý định?

Hãy hình dung dữ liệu được tổ chức theo cây phân cấp:

```text
Database
└── Table: Orders
    ├── Page 1
    │   ├── Row 1
    │   └── Row 2
    └── Page 2
        ├── Row 3
        └── Row 4
```

Một giao dịch có thể khóa toàn bộ bảng `Orders`, trong khi giao dịch khác chỉ khóa dòng `Row 3`. Nếu hệ quản trị chỉ ghi nhận khóa ở đúng đối tượng được yêu cầu, nó có thể không nhận ra rằng khóa bảng đang xung đột với khóa dòng nằm bên trong bảng.

Ví dụ:

- Giao dịch T1 muốn đọc toàn bộ bảng `Orders` và yêu cầu khóa chia sẻ (`S`) trên bảng.
- Giao dịch T2 muốn cập nhật riêng `Row 3` và yêu cầu khóa độc quyền (`X`) trên dòng.

Hai yêu cầu này phải xung đột: khi T1 đang đọc toàn bộ bảng theo một khóa chia sẻ ở cấp bảng, T2 không thể âm thầm sửa một dòng bên trong. Nhưng nếu T2 chỉ đặt `X` ở dòng mà không để lại dấu hiệu trên bảng, bộ quản lý khóa khó phát hiện xung đột với khóa cấp bảng.

Với khóa ý định, T2 phải đặt `IX` (Intention Exclusive) trên các nút cha trước khi đặt `X` trên dòng. Khi T1 yêu cầu `S` trên bảng, hệ quản trị thấy `S` xung đột với `IX` đang tồn tại và buộc T1 chờ. Không cần quét mọi dòng để tìm khóa độc quyền.

Khóa ý định vì thế có hai vai trò:

1. Thông báo loại khóa mà giao dịch dự định lấy ở các cấp thấp hơn.
2. Giúp khóa ở cấp cao phát hiện xung đột với hoạt động khóa ở cấp thấp thông qua ma trận tương thích tại nút cha.

## 2. Các cấp độ khóa trong một hệ phân cấp

Một hệ quản trị có thể tổ chức đối tượng khóa theo nhiều cấp, chẳng hạn:

| Cấp | Đối tượng ví dụ | Phạm vi được bảo vệ |
|---|---|---|
| Database | Cơ sở dữ liệu bán hàng | Toàn bộ cơ sở dữ liệu hoặc một nhánh lớn bên dưới |
| Table | Bảng `Orders` | Bảng và các đối tượng dữ liệu thuộc bảng |
| Page | Trang chứa một nhóm dòng | Các dòng nằm trong trang |
| Row | Dòng `Order` cụ thể | Một dòng dữ liệu |

Đây là mô hình minh họa phổ biến. Một hệ quản trị thực tế có thể có thêm cấp phân vùng, extent hoặc cấu trúc lưu trữ khác; cách tổ chức và tên gọi cụ thể phụ thuộc sản phẩm.

Khóa ở cấp bảng được gọi là khóa thô (coarse-grained lock), còn khóa ở cấp dòng là khóa mịn (fine-grained lock). Khóa thô giảm số lượng mục khóa phải quản lý, nhưng thường hạn chế nhiều giao dịch hơn. Khóa mịn tăng khả năng đồng thời, nhưng làm tăng số lượng khóa, chi phí tra cứu, bộ nhớ và công việc kiểm tra xung đột.

Trong mô hình khóa nhiều cấp (multiple-granularity locking), mỗi đối tượng là một nút trong cây. Muốn khóa một nút con, giao dịch phải khai báo ý định phù hợp trên đường đi từ gốc đến nút đó. Nhờ vậy, một yêu cầu khóa tại nút cha có thể được kiểm tra mà không cần xem toàn bộ hậu duệ.

## 3. Năm chế độ khóa chính

Ngoài hai khóa dữ liệu quen thuộc `S` và `X`, mô hình khóa nhiều cấp sử dụng ba chế độ ý định: `IS`, `IX` và `SIX`.

| Chế độ | Tên đầy đủ | Ý nghĩa |
|---|---|---|
| `S` | Shared | Khóa chia sẻ trực tiếp trên nút hiện tại; nhiều giao dịch có thể cùng đọc theo phạm vi khóa |
| `X` | Exclusive | Khóa độc quyền trực tiếp trên nút hiện tại; giao dịch khác không thể lấy khóa xung đột trên phạm vi đó |
| `IS` | Intention Shared | Giao dịch dự định lấy khóa chia sẻ trên một hoặc nhiều nút con |
| `IX` | Intention Exclusive | Giao dịch dự định lấy khóa độc quyền trên một hoặc nhiều nút con |
| `SIX` | Shared and Intention Exclusive | Giao dịch giữ khóa chia sẻ trên nút hiện tại và dự định lấy khóa độc quyền trên một số nút con |

### 3.1. Shared lock — `S`

`S` cho phép giao dịch đọc đối tượng được khóa. Nhiều giao dịch có thể cùng giữ `S` trên một đối tượng vì các thao tác đọc không trực tiếp sửa dữ liệu. Một yêu cầu `X` trên cùng đối tượng sẽ phải chờ khi `S` vẫn còn hiệu lực.

Ví dụ, T1 và T2 cùng đọc bảng `Customers` bằng khóa `S` trên bảng. Hai khóa `S` tương thích nên cả hai có thể tiếp tục đọc. Nếu T3 muốn cập nhật toàn bộ bảng bằng `X`, yêu cầu đó xung đột với các khóa `S` hiện tại.

### 3.2. Exclusive lock — `X`

`X` cho phép giao dịch sửa đối tượng và loại trừ các khóa xung đột từ giao dịch khác trên cùng đối tượng. Một dòng đang được cập nhật thường được bảo vệ bằng `X` ở cấp dòng.

Ví dụ, T1 lấy `X` trên dòng có `order_id = 42`. T2 không thể đồng thời lấy `S` hoặc `X` trên chính dòng đó cho đến khi xung đột được giải quyết. T2 vẫn có thể thao tác trên một dòng khác nếu các khóa ở những cấp liên quan tương thích.

### 3.3. Intention Shared — `IS`

`IS` thông báo rằng giao dịch sẽ lấy khóa chia sẻ ở một cấp thấp hơn. Bản thân `IS` không có nghĩa giao dịch đã khóa chia sẻ tất cả dòng bên dưới.

Ví dụ, để đọc một dòng trong bảng, giao dịch có thể đặt `IS` trên database, `IS` trên bảng và trang, rồi đặt `S` trực tiếp trên dòng cần đọc.

### 3.4. Intention Exclusive — `IX`

`IX` thông báo rằng giao dịch dự định lấy khóa độc quyền ở một hoặc nhiều cấp thấp hơn. Nó không tự động khóa độc quyền tất cả dòng trong bảng.

Ví dụ, để cập nhật một dòng, giao dịch đặt `IX` trên database, bảng và trang, sau đó đặt `X` trên dòng cần cập nhật. Một giao dịch khác vẫn có thể lấy các khóa tương thích và thao tác trên những dòng khác.

### 3.5. Shared and Intention Exclusive — `SIX`

`SIX` kết hợp hai ý nghĩa:

- Giao dịch giữ `S` trên nút hiện tại.
- Giao dịch có ý định lấy `X` trên một số nút con.

Chế độ này hữu ích khi giao dịch cần đọc toàn bộ một phạm vi, đồng thời cập nhật một số đối tượng nhỏ bên trong phạm vi đó. Ví dụ, T1 cần quét toàn bộ bảng `Orders` để tính toán, rồi cập nhật một vài dòng thỏa điều kiện. T1 có thể giữ `SIX` trên bảng và lấy `X` trên từng dòng cần sửa.

`SIX` không có nghĩa tất cả dòng con đã được khóa `X`. Nó ghi nhận khóa chia sẻ ở nút hiện tại và ý định khóa độc quyền ở các cấp thấp hơn; những dòng được sửa vẫn cần khóa `X` cụ thể.

## 4. Ma trận tương thích khóa

Hai khóa tương thích khi chúng có thể cùng tồn tại trên một nút mà không vi phạm quy tắc bảo vệ dữ liệu. Ma trận dưới đây là ma trận chuẩn của mô hình khóa nhiều cấp với năm chế độ `IS`, `IX`, `S`, `SIX` và `X`.

| Khóa đang giữ \ Khóa mới | `IS` | `IX` | `S` | `SIX` | `X` |
|---|:---:|:---:|:---:|:---:|:---:|
| `IS` | ✓ | ✓ | ✓ | ✓ | ✗ |
| `IX` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `S` | ✓ | ✗ | ✓ | ✗ | ✗ |
| `SIX` | ✓ | ✗ | ✗ | ✗ | ✗ |
| `X` | ✗ | ✗ | ✗ | ✗ | ✗ |

Ma trận đối xứng: nếu `A` tương thích với `B` thì `B` cũng tương thích với `A`. Ký hiệu ✓ nghĩa là có thể cùng tồn tại; ✗ nghĩa là yêu cầu mới phải chờ hoặc được xử lý theo chính sách khóa của hệ quản trị.

Một số cặp quan trọng cần hiểu rõ:

- `IS` tương thích với `IS`, `IX`, `S`, `SIX`. Một giao dịch chỉ dự định đọc một số dòng không nhất thiết phải chặn giao dịch khác đang đọc hoặc cập nhật những dòng khác.
- `IX` tương thích với `IX`. Nhiều giao dịch có thể cùng dự định cập nhật các dòng khác nhau trong một bảng; xung đột thực tế được kiểm tra tiếp ở cấp dòng.
- `S` không tương thích với `IX`. Một giao dịch đang đọc cả bảng theo khóa `S` phải chặn giao dịch khác khai báo ý định cập nhật các dòng trong bảng.
- `SIX` chỉ tương thích với `IS` trong các chế độ được liệt kê. Nó cho phép giao dịch khác khai báo ý định đọc ở cấp thấp hơn, nhưng ngăn một giao dịch khác lấy `IX` để cập nhật các dòng trong cùng phạm vi.
- `X` không tương thích với bất kỳ chế độ nào khác. Đây là chế độ loại trừ hoàn toàn trên chính nút được khóa.

Ma trận được kiểm tra tại từng nút có khóa. Hai giao dịch có `IX` trên cùng bảng vẫn có thể cập nhật đồng thời nếu chúng lấy `X` trên hai dòng khác nhau và không có xung đột ở các cấp thấp hơn. Ngược lại, nếu chúng cùng yêu cầu `X` trên một dòng thì yêu cầu sau phải chờ.

## 5. Quy tắc lấy và nhả khóa theo cây

Khóa nhiều cấp cần tuân theo thứ tự để khóa ở cấp cha luôn phản ánh chính xác hoạt động ở cấp con.

### 5.1. Lấy khóa từ gốc xuống lá

Giao dịch bắt đầu tại nút gốc rồi đi dần xuống nút cần truy cập. Trước khi khóa một nút con, giao dịch phải có khóa ý định phù hợp trên nút cha.

Các quy tắc thường dùng trong giao thức khóa nhiều cấp:

1. Nút gốc có thể được khóa bằng một trong các chế độ phù hợp với thao tác của giao dịch.
2. Muốn lấy `S` hoặc `IS` trên một nút, giao dịch phải có `IS` hoặc `IX` trên nút cha. `SIX` ở nút cha cũng mang thành phần ý định độc quyền nên có thể đáp ứng yêu cầu đi xuống.
3. Muốn lấy `X`, `IX` hoặc `SIX` trên một nút, giao dịch phải có `IX` hoặc `SIX` trên nút cha.
4. Nếu một nút cha đã được khóa trực tiếp bằng `S` hoặc `X`, khóa đó đã bảo vệ phạm vi bên dưới theo ngữ nghĩa phân cấp; thường không cần lấy thêm khóa riêng trên các nút con nằm trong phạm vi đã được bảo vệ.

Ví dụ, T1 cập nhật một dòng trong `Orders`:

```text
IX(Database)
  └── IX(Orders)
      └── IX(Page 2)
          └── X(Row 3)
```

Mỗi khóa ý định trên đường đi cho bộ quản lý khóa biết rằng T1 sẽ khóa độc quyền ở cấp thấp hơn. Khi T1 lấy `X(Row 3)`, nó đã có đủ khóa ý định ở các nút cha.

Để chỉ đọc dòng đó, một giao dịch khác có thể đi theo đường tương ứng với `IS`:

```text
IS(Database)
  └── IS(Orders)
      └── IS(Page 2)
          └── S(Row 3)
```

Hai đường khóa có thể cùng tồn tại ở các nút cha vì `IX` tương thích với `IS`. Tuy nhiên, `X(Row 3)` xung đột với `S(Row 3)`, nên giao dịch đọc dòng 3 phải chờ nếu T1 vẫn giữ khóa độc quyền.

### 5.2. Nhả khóa từ lá lên gốc

Khi giao dịch kết thúc hoặc không còn cần một khóa, nó phải nhả khóa ở cấp thấp trước rồi mới nhả khóa ở cấp cha. Không được nhả khóa cha trong khi vẫn còn khóa con thuộc phạm vi đó.

Ví dụ, nếu T1 vẫn giữ `X(Row 3)` nhưng đã nhả `IX(Orders)`, một giao dịch khác có thể không còn nhìn thấy dấu hiệu rằng T1 đang cập nhật dòng bên trong bảng. Quy tắc nhả từ dưới lên ngăn trạng thái không nhất quán này.

Trong giao thức khóa nhiều cấp kết hợp với khóa hai pha (two-phase locking), giao dịch không lấy thêm khóa mới sau khi đã bắt đầu giai đoạn nhả khóa. Điều này giúp duy trì tính chất khóa cần thiết cho khả năng tuần tự hóa. Các hệ quản trị có thể triển khai chi tiết khác nhau, nhưng nguyên tắc phối hợp khóa cha-con vẫn cần được bảo đảm.

## 6. Ví dụ phối hợp nhiều giao dịch

Giả sử bảng `Orders` có các dòng 42, 43 và 44. Các dòng này có thể nằm trong cùng một trang.

### Tình huống A: Hai giao dịch cập nhật hai dòng khác nhau

T1 cập nhật dòng 42, T2 cập nhật dòng 43:

```text
T1: IX(Database) -> IX(Orders) -> IX(Page 3) -> X(Row 42)
T2: IX(Database) -> IX(Orders) -> IX(Page 3) -> X(Row 43)
```

Ở database, bảng và trang, `IX` của T1 tương thích với `IX` của T2. Hai khóa `X` nằm trên hai dòng khác nhau nên không xung đột. Hai giao dịch có thể tiếp tục đồng thời.

Nếu T2 cũng yêu cầu `X(Row 42)`, hai khóa độc quyền cùng dòng sẽ xung đột và một giao dịch phải chờ giao dịch còn lại nhả khóa.

### Tình huống B: Một giao dịch đọc toàn bảng, giao dịch khác cập nhật một dòng

T1 muốn đọc toàn bộ `Orders`:

```text
T1: IS(Database) -> S(Orders)
```

T2 muốn cập nhật dòng 42:

```text
T2: IX(Database) -> IX(Orders) -> IX(Page 3) -> X(Row 42)
```

T1 có `S(Orders)`, còn T2 cần `IX(Orders)`. Hai chế độ này không tương thích. Vì vậy, T2 phải chờ trước khi đi xuống các cấp thấp hơn để lấy khóa dòng. T1 có thể đọc bảng trong khi dữ liệu không bị T2 sửa đồng thời.

### Tình huống C: Một giao dịch đọc toàn bảng và cập nhật một số dòng

T1 cần đọc bảng `Orders` rồi cập nhật dòng 42 và 44. T1 có thể sử dụng `SIX` trên bảng:

```text
T1: IX(Database)
    -> SIX(Orders)
    -> IX(Page 3)
    -> X(Row 42)
    -> X(Row 44)
```

`SIX(Orders)` biểu thị việc T1 giữ khóa chia sẻ ở cấp bảng và có ý định lấy khóa độc quyền ở các cấp thấp hơn. T1 lấy `X` riêng trên từng dòng cần sửa.

Một giao dịch T2 chỉ đọc dòng 43 có thể dùng `IS(Orders)` rồi lấy `S(Row 43)`, vì `SIX` tương thích với `IS`. T2 vẫn phải kiểm tra khóa tại dòng 43. Nếu T2 muốn cập nhật dòng 43, nó cần `IX(Orders)`, chế độ này xung đột với `SIX(Orders)` nên phải chờ.

## 7. Khóa ý định và nâng cấp phạm vi khóa

Khi giao dịch lấy khóa trên rất nhiều dòng, chi phí theo dõi từng khóa có thể trở nên lớn. Hệ quản trị có thể thực hiện **nâng cấp phạm vi khóa (lock escalation)**: thay nhiều khóa ở cấp nhỏ bằng một khóa ở cấp lớn hơn có phạm vi bao phủ tương đương.

Ví dụ, một giao dịch đọc rất nhiều dòng có thể được chuyển từ nhiều khóa `S` ở cấp dòng sang một khóa `S` ở cấp bảng. Một giao dịch cập nhật nhiều dòng có thể được chuyển sang khóa độc quyền ở cấp lớn hơn, tùy chính sách của hệ quản trị và tập khóa đang nắm giữ.

Nâng cấp khóa có lợi khi giảm được số lượng mục khóa và chi phí quản lý. Tuy nhiên, khóa ở cấp lớn có thể làm nhiều giao dịch khác phải chờ, kể cả khi chúng chỉ cần truy cập những dòng khác nhau. Vì vậy, nâng cấp khóa là sự đánh đổi giữa chi phí quản lý khóa và mức độ đồng thời.

Khóa ý định và nâng cấp khóa có quan hệ nhưng là hai cơ chế khác nhau:

| Cơ chế | Mục đích | Điều thay đổi |
|---|---|---|
| Khóa ý định (`IS`, `IX`) | Công bố ý định khóa ở cấp thấp hơn để phối hợp với khóa cấp cao | Thêm dấu hiệu trên các nút cha; khóa dữ liệu chi tiết vẫn nằm ở nút con |
| Nâng cấp khóa | Giảm số lượng khóa nhỏ mà giao dịch đang giữ | Thay nhiều khóa cấp nhỏ bằng một khóa có phạm vi lớn hơn |

`SIX` cũng không phải là nâng cấp khóa theo nghĩa chung. Đây là một chế độ khóa xác định, dùng khi giao dịch cần khóa chia sẻ ở nút hiện tại và khóa độc quyền ở một số nút con.

## 8. Lợi ích và chi phí của khóa nhiều cấp

Khóa nhiều cấp cho phép hệ quản trị cân bằng giữa phạm vi khóa và khả năng đồng thời:

- **Tăng khả năng đồng thời:** các giao dịch có thể khóa những dòng khác nhau trong cùng bảng nếu các khóa ý định ở cấp cha tương thích.
- **Phối hợp khóa ở nhiều phạm vi:** yêu cầu khóa bảng có thể phát hiện hoạt động khóa dòng thông qua `IS` hoặc `IX` ở cấp bảng.
- **Giảm công việc kiểm tra:** bộ quản lý khóa có thể kiểm tra tương thích tại các nút trên đường đi thay vì duyệt toàn bộ đối tượng con.
- **Hỗ trợ lựa chọn phạm vi phù hợp:** giao dịch đọc toàn bảng có thể dùng khóa cấp bảng; giao dịch cập nhật ít dòng có thể dùng khóa cấp dòng.
- **Tăng độ phức tạp quản lý:** hệ quản trị phải duy trì khóa trên nhiều cấp, kiểm tra thứ tự lấy/nhả khóa và xử lý chuyển đổi chế độ khóa.
- **Có thể giảm đồng thời khi khóa quá thô:** một khóa ở cấp bảng có thể khiến nhiều giao dịch độc lập trên các dòng khác nhau phải chờ.

Khóa ý định không tự loại bỏ deadlock. Hai giao dịch vẫn có thể chờ lẫn nhau nếu chúng lấy nhiều khóa theo thứ tự không phù hợp. Hệ quản trị vẫn cần cơ chế phát hiện deadlock, timeout hoặc chính sách xử lý chờ khóa. Việc thống nhất thứ tự truy cập đối tượng có thể giảm nguy cơ deadlock ở cấp ứng dụng.

Ngoài ra, khóa nhiều cấp giải quyết việc phối hợp khóa giữa các nút trong cây dữ liệu. Nó không tự thay thế mọi cơ chế bảo vệ truy vấn theo điều kiện. Chẳng hạn, việc ngăn bản ghi mới xuất hiện trong một khoảng giá trị (phantom) còn phụ thuộc mức cô lập giao dịch và các cơ chế khóa phạm vi hoặc predicate lock mà hệ quản trị hỗ trợ.

## 9. Những nhầm lẫn thường gặp

**`IS` có nghĩa là đã khóa chia sẻ tất cả dòng bên dưới.** Không đúng. `IS` chỉ thông báo ý định lấy khóa chia sẻ ở cấp thấp hơn. Giao dịch vẫn phải lấy `S` trên các đối tượng cụ thể mà nó cần bảo vệ.

**`IX` có nghĩa là đã khóa độc quyền toàn bộ bảng.** Không đúng. `IX` cho biết giao dịch dự định lấy khóa độc quyền ở một hoặc nhiều nút con. Các giao dịch khác vẫn có thể có `IX` tương thích trên cùng bảng và cập nhật những dòng khác nhau.

**Có thể lấy khóa dòng mà không cần khóa ý định ở các nút cha.** Điều này vi phạm giao thức khóa nhiều cấp. Khóa ý định giúp các yêu cầu ở cấp bảng hoặc cấp cao hơn nhận ra hoạt động khóa đang diễn ra ở bên dưới.

**`SIX` giống `S` hoặc `IX`.** `SIX` kết hợp khóa chia sẻ ở nút hiện tại với ý định khóa độc quyền ở các nút con. Nó phù hợp với giao dịch cần đọc phạm vi lớn và cập nhật một phần phạm vi đó.

**Khóa ý định ngăn được mọi deadlock.** Không đúng. Khóa ý định giúp kiểm tra tương thích giữa các cấp; deadlock vẫn có thể xảy ra khi nhiều giao dịch chờ tài nguyên của nhau.

## 10. Cách đọc một chuỗi khóa

Khi xem log khóa hoặc phân tích một giao dịch, hãy đọc từ gốc xuống nút dữ liệu:

1. Xác định đối tượng gốc và các cấp trung gian mà giao dịch đi qua.
2. Kiểm tra mỗi nút cha có `IS`, `IX` hoặc `SIX` phù hợp với khóa ở nút con hay không.
3. Xác định khóa dữ liệu trực tiếp (`S` hoặc `X`) nằm ở cấp nào và bảo vệ đối tượng nào.
4. Đối chiếu khóa của các giao dịch khác bằng ma trận tương thích tại từng nút có chung phạm vi.
5. Kiểm tra thứ tự nhả khóa: nút con phải được nhả trước nút cha.
6. Nếu thấy nhiều khóa nhỏ được thay bằng khóa lớn, xem xét liệu hệ quản trị đã nâng cấp phạm vi khóa hay chưa.

Ví dụ, chuỗi sau cho biết giao dịch có ý định cập nhật một dòng cụ thể:

```text
IX(Database) -> IX(Orders) -> IX(Page 3) -> X(Row 42)
```

Đọc chuỗi này theo từng cấp sẽ cho biết T1 không khóa độc quyền toàn bộ database hoặc toàn bộ bảng. T1 chỉ khai báo ý định cập nhật ở các cấp cha và lấy khóa độc quyền trực tiếp trên `Row 42`. Nhờ vậy, giao dịch khác vẫn có thể làm việc trên các dòng khác nếu đường khóa và khóa tại dòng đó tương thích.

Khi phân tích hành vi của một hệ quản trị cụ thể, cần đối chiếu thêm tài liệu của sản phẩm về tên chế độ khóa, cấp khóa được hỗ trợ, chính sách nâng cấp và mức cô lập. Mô hình `IS`/`IX`/`S`/`SIX`/`X` cung cấp nền tảng để hiểu cách phối hợp nhiều cấp, còn chi tiết triển khai có thể khác nhau giữa các hệ quản trị cơ sở dữ liệu.
