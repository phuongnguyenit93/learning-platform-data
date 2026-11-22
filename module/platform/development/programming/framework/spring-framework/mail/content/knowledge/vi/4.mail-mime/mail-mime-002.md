# Content-Type, charset và Content-Transfer-Encoding

Một email có thể chứa văn bản tiếng Việt, HTML, hình ảnh, hóa đơn PDF và nhiều tệp đính kèm. Nhưng SMTP ban đầu được thiết kế quanh việc vận chuyển dữ liệu dạng văn bản với các giới hạn về ký tự và dòng. **MIME (Multipurpose Internet Mail Extensions)** bổ sung cách mô tả loại nội dung, bộ mã ký tự và cách biểu diễn dữ liệu để nhiều hệ thống email có thể truyền và đọc đúng thông điệp.

Ba khái niệm cần tách biệt là:

- **`Content-Type`**: phần dữ liệu này *là loại nội dung gì*? Văn bản thuần, HTML, PDF, hình ảnh hay một tập hợp nhiều phần?
- **`charset`**: nếu đây là văn bản, *các byte được diễn giải thành ký tự theo bộ mã nào*? Ví dụ `UTF-8`.
- **`Content-Transfer-Encoding`**: *các byte của nội dung được biểu diễn theo cách nào để vận chuyển qua môi trường email*? Ví dụ `quoted-printable` hoặc `base64`.

Ba thông tin giải quyết ba câu hỏi khác nhau. Đặt đúng `charset` nhưng khai báo sai `Content-Transfer-Encoding` vẫn khiến mail client hiển thị sai; khai báo `text/html` nhưng chuyển nội dung HTML không đúng cấu trúc cũng có thể làm người nhận thấy mã HTML dưới dạng chữ.

Trong **Spring Framework Mail**, `JavaMailSender` và `MimeMessageHelper` giúp tạo các MIME message đúng định dạng. Hiểu các header này giúp lựa chọn API thích hợp và chẩn đoán lỗi email bị mất dấu, hiện ký tự lạ, hỏng attachment hoặc hiển thị HTML sai.

## 1. Từ Java String đến email người nhận nhìn thấy

Một `String` trong Java chứa ký tự Unicode ở mức mô hình chuỗi. Để gửi qua giao thức, hệ thống phải biến chuỗi thành byte, có thể chuyển các byte đó sang biểu diễn an toàn cho đường truyền, rồi bên nhận thực hiện quá trình ngược lại.

```text
Ứng dụng Spring / Java
   |
   | String: "Chào bạn"
   v
[MIME text part]
   |
   | charset=UTF-8: ký tự -> byte UTF-8
   v
  43 68 C3 A0 6F 20 62 E1 BA A1 6E
   |
   | Content-Transfer-Encoding: quoted-printable
   v
  Ch=C3=A0o b=E1=BA=A1n
   |
   | SMTP chuyển nội dung đã đóng gói MIME
   v
[Hệ thống nhận / Mail client]
   |
   | Giải mã quoted-printable -> khôi phục byte
   | Giải mã UTF-8 -> khôi phục Unicode
   v
Người đọc thấy: "Chào bạn"
```

Đây là luồng của **một phần văn bản**; nếu dùng `base64`, phần chuyển đổi để vận chuyển khác đi nhưng quá trình khôi phục vẫn có hai bước. Với file PDF hay hình ảnh, hệ thống có thể dùng base64 để mang byte qua đường truyền, nhưng không diễn giải các byte đó như ký tự UTF-8.

### Vai trò của từng header trong một ví dụ

```eml
MIME-Version: 1.0
From: notifications@example.org
To: customer@example.net
Subject: Hello
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n
```

- `MIME-Version: 1.0` báo thông điệp sử dụng MIME.
- `Content-Type: text/plain` cho biết phần thân này là văn bản thuần.
- `charset=UTF-8` cho biết cách ánh xạ byte thành ký tự văn bản.
- `Content-Transfer-Encoding: quoted-printable` cho biết phần thân trên đường truyền cần được giải mã quoted-printable để lấy lại byte gốc.

Đoạn trên là một ví dụ email dạng thô (*raw MIME message*). Dòng trống giữa các header và body là một phần của cấu trúc message. Trong bản tin thực, các dòng được phân cách theo quy ước giao thức email; ký hiệu xuống dòng của trình soạn thảo Markdown chỉ dùng để minh họa.

## 2. `Content-Type`: dữ liệu thuộc loại nào?

`Content-Type` là một header MIME mô tả **media type** của phần nội dung. Một giá trị thường có dạng:

```text
Content-Type: type/subtype; parameter=value
```

Trong đó:

- `type` là nhóm nội dung, như `text`, `image`, `application` hoặc `multipart`.
- `subtype` mô tả kiểu cụ thể trong nhóm, như `plain`, `html`, `pdf` hoặc `mixed`.
- `parameter` bổ sung thông tin phụ thuộc loại nội dung; phổ biến nhất là `charset` cho văn bản và `boundary` cho `multipart`.

Một số giá trị thường gặp:

| `Content-Type` | Ý nghĩa | Tình huống email |
| --- | --- | --- |
| `text/plain; charset=UTF-8` | Văn bản thuần dùng UTF-8 | Thư xác nhận đơn hàng ở dạng text |
| `text/html; charset=UTF-8` | Nội dung HTML dùng UTF-8 | Email giao dịch được trình bày bằng HTML |
| `multipart/alternative; boundary="..."` | Nhiều phiên bản thay thế cùng một nội dung | Kèm cả text thuần và HTML |
| `multipart/mixed; boundary="..."` | Nhiều thành phần độc lập trong cùng message | Phần thư chính kèm PDF |
| `multipart/related; boundary="..."` | Các phần có quan hệ nội bộ | HTML tham chiếu hình ảnh inline qua CID |
| `application/pdf` | Dữ liệu PDF | Hóa đơn đính kèm |
| `image/png` | Dữ liệu hình PNG | Hình ảnh inline hoặc attachment |
| `application/octet-stream` | Byte nhị phân không có loại cụ thể hơn | Tệp đính kèm chưa xác định chính xác media type |

**`Content-Type` không phải `Content-Disposition`.** `Content-Disposition: attachment` gợi ý client nên cung cấp tệp như một attachment, còn `Content-Disposition: inline` gợi ý hiển thị trong nội dung khi có thể. `Content-Type` cho biết *nội dung là gì*; `Content-Disposition` liên quan đến *cách trình bày hoặc xử lý*.

Ví dụ:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"
```

Ở đây PDF là kiểu dữ liệu; `attachment` là cách gắn tệp vào email; `base64` là cách biểu diễn các byte để vận chuyển.

### 2.1. `text/plain` và `text/html` khác nhau ra sao?

Hai nội dung bên dưới trông giống nhau khi đọc source nhưng yêu cầu hiển thị khác nhau:

```text
Content-Type: text/plain; charset=UTF-8

<strong>Đơn hàng đã xác nhận</strong>
```

Mail client có thể hiển thị nguyên các ký tự `<strong>` và `</strong>` vì nội dung được khai báo là **văn bản thuần**.

```text
Content-Type: text/html; charset=UTF-8

<strong>Đơn hàng đã xác nhận</strong>
```

Mail client có thể hiển thị câu chữ in đậm khi hỗ trợ HTML và cho phép cách hiển thị đó. Không phải mọi thuộc tính CSS, hình ảnh hay script trong HTML email đều được client hỗ trợ; nhiều client chủ động hạn chế nội dung vì bảo mật và quyền riêng tư.

### 2.2. `multipart` là một container

`multipart/*` không diễn giải toàn bộ body như một khối text hoặc PDF. Nó chỉ ra rằng body chứa **nhiều MIME part**, mỗi part có **header riêng**, **body riêng**, và được tách bởi ký hiệu `boundary`.

Các kiểu có ý nghĩa khác nhau:

- **`multipart/alternative`:** các phiên bản thay thế cho cùng một thông điệp, điển hình là text và HTML. Client chọn bản nó có thể và muốn hiển thị.
- **`multipart/mixed`:** tập hợp nhiều phần riêng biệt, thường là nội dung thư chính cộng với attachment.
- **`multipart/related`:** nội dung có quan hệ với nhau, chẳng hạn HTML và hình inline được tham chiếu bằng `cid:...`.

Một thư có HTML và tệp đính kèm có thể lồng `multipart/alternative` bên trong `multipart/mixed`. Khi dùng `MimeMessageHelper` đúng cách, thư viện sẽ tạo cấu trúc và boundary giúp ứng dụng.

### 2.3. `boundary` dùng để tách MIME part

Ví dụ đơn giản với hai phiên bản text/HTML:

```eml
MIME-Version: 1.0
From: store@example.org
To: customer@example.net
Subject: Order confirmed
Content-Type: multipart/alternative; boundary="alternative-123"

--alternative-123
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n, =C4=91=C6=A1n h=C3=A0ng =C4=91=C3=A3 x=C3=A1c nh=E1=BA=ADn.

--alternative-123
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Ch=C3=A0o b=E1=BA=A1n, <strong>=C4=91=C6=A1n h=C3=A0ng</strong> =C4=91=C3=A3 x=C3=A1c nh=E1=BA=ADn.</p>

--alternative-123--
```

Chuỗi `boundary="alternative-123"` được khai báo trong header của container. Mỗi phần bắt đầu bằng `--alternative-123` và marker `--alternative-123--` đóng multipart. Trong thư thật, boundary nên do thư viện MIME tạo để không trùng ngẫu nhiên với dữ liệu bên trong.

**Lưu ý:** mỗi child part có thể khai báo `Content-Type`, `charset` và `Content-Transfer-Encoding` khác nhau. Không được mặc định mọi phần sẽ dùng charset/encoding của parent `multipart`.

## 3. `charset`: cách chuyển đổi giữa ký tự và byte

**Character set / character encoding** mô tả phép chuyển đổi giữa chuỗi ký tự và các byte lưu trữ hay vận chuyển. Với nội dung văn bản, MIME thường khai báo qua parameter `charset` trong `Content-Type`:

```text
Content-Type: text/plain; charset=UTF-8
```

Nếu cùng dãy byte được đọc theo charset khác nhau, người nhận có thể thấy ký tự khác hoàn toàn so với người gửi.

### 3.1. Vì sao nên chọn UTF-8?

**UTF-8** biểu diễn được Unicode, bao gồm tiếng Việt có dấu, ký tự của nhiều ngôn ngữ và biểu tượng. Nó tương thích với ASCII ở vùng cơ bản, được các hệ thống hiện đại hỗ trợ rộng rãi và là lựa chọn phổ biến cho email ứng dụng.

Ví dụ chuỗi:

```text
Chào bạn
```

Khi mã hóa UTF-8, các byte ở dạng hexadecimal là:

```text
43 68 C3 A0 6F 20 62 E1 BA A1 6E
```

Chữ `à` chiếm hai byte `C3 A0`; chữ `ạ` chiếm ba byte `E1 BA A1`. Điều này cho thấy **số ký tự, số byte UTF-8 và số ký tự sau transfer encoding không phải cùng một đại lượng**.

Nếu ứng dụng đã tạo byte UTF-8 nhưng một mail client giải mã nhầm bằng bộ mã khác, người đọc có thể thấy chữ như `ChÃ o` hoặc ký tự thay thế `�`. Trường hợp này khác với việc có dấu `=C3=A0` hiển thị nguyên văn: dấu hiệu thứ hai có thể gợi ý rằng quoted-printable chưa được giải mã.

### 3.2. Khai báo charset phải khớp byte thực tế

Một phần MIME có header:

```text
Content-Type: text/plain; charset=UTF-8
```

phải chứa **byte của văn bản theo UTF-8** sau khi đã giải mã transfer encoding. Nếu byte thực tế được tạo bằng một charset khác nhưng header vẫn ghi UTF-8, mail client không thể tự sửa sai một cách đáng tin cậy.

Các charset truyền thống như `ISO-8859-1`, `windows-1252` hoặc các bộ mã địa phương còn có thể gặp trong email cũ. Chỉ dùng chúng khi thật sự cần tương thích với nguồn dữ liệu đang sử dụng bộ mã đó; không nên dựa vào cơ chế đoán charset của mail client.

Trong MIME cổ điển, nếu `text/plain` không chỉ rõ `charset`, giá trị mặc định theo chuẩn là `US-ASCII`. Một số client cố đoán bộ mã để hiển thị thư cũ, nhưng kết quả không ổn định. Vì vậy, với văn bản tiếng Việt, hãy **khai báo `charset=UTF-8` rõ ràng**.

### 3.3. Charset chỉ có ý nghĩa với phần dữ liệu cần diễn giải như văn bản

Thư đính kèm một ảnh PNG:

```text
Content-Type: image/png
Content-Transfer-Encoding: base64
```

Các byte PNG không cần parameter `charset=UTF-8`. Tương tự, dữ liệu PDF hoặc tệp ZIP không phải tự nhiên trở thành “văn bản UTF-8” chỉ vì ứng dụng Java đang xử lý một đường dẫn hoặc tên file dưới dạng `String`.

Tên file có dấu trong MIME lại là vấn đề **mã hóa giá trị tham số header**, thường được thư viện xử lý theo quy tắc phù hợp; không nên tự nối byte UTF-8 thô vào header rồi giả định mọi client hiểu.

## 4. `Content-Transfer-Encoding`: cách biểu diễn byte trên đường truyền

Sau khi nội dung văn bản đã được biến thành byte theo charset, MIME có thể dùng **Content-Transfer-Encoding (CTE)** để biểu diễn byte dưới một dạng phù hợp với vận chuyển email.

Header ví dụ:

```text
Content-Transfer-Encoding: quoted-printable
```

Đây **không phải** thuật toán chuyển ngôn ngữ sang byte và cũng **không phải** cơ chế nén hay mã hóa bảo mật. Base64 hoặc quoted-printable không giữ bí mật nội dung: bất kỳ client nào cũng có thể giải mã.

| CTE | Cách hoạt động | Phù hợp với | Ghi chú |
| --- | --- | --- | --- |
| **`7bit`** | Body chỉ dùng dữ liệu phù hợp ràng buộc 7-bit của email | Văn bản ASCII đơn giản | Không biểu diễn byte UTF-8 không thuộc ASCII một cách trực tiếp |
| **`8bit`** | Cho phép byte có bit cao trong body theo môi trường hỗ trợ | Văn bản chứa byte không phải ASCII khi transport hỗ trợ | Thường cần hạ tầng hỗ trợ `8BITMIME` |
| **`binary`** | Biểu diễn byte không có ràng buộc kiểu dòng như 7bit/8bit | Môi trường đặc biệt hỗ trợ truyền binary | Không phải lựa chọn mặc định cho email liên miền |
| **`quoted-printable`** | Giữ ký tự ASCII dễ đọc; byte khác hoặc ký tự đặc biệt mã thành `=HH` | Nội dung văn bản, đặc biệt khi phần lớn là ASCII | Cần giải mã trước khi áp dụng charset |
| **`base64`** | Mã hóa mọi byte bằng bảng chữ cái ASCII | PDF, ảnh, ZIP và cả văn bản có nhiều byte không phải ASCII | Tăng kích thước dữ liệu khoảng một phần ba, chưa kể xuống dòng |

### 4.1. `7bit`

`7bit` là cách phù hợp với mô hình truyền thư truyền thống khi body chứa các ký tự ASCII trong giới hạn dòng được giao thức cho phép. Ví dụ:

```eml
Content-Type: text/plain; charset=US-ASCII
Content-Transfer-Encoding: 7bit

Your order is confirmed.
```

Nếu body chứa chữ `ă`, `ộ`, `ữ` ở dạng UTF-8, những byte tương ứng không còn nằm hoàn toàn trong ASCII. Không được giữ nguyên byte không-ASCII nhưng tuyên bố `7bit`.

### 4.2. `8bit` và `binary`

`8bit` cho phép các byte có bit cao trong phần body khi đường truyền và máy chủ SMTP hỗ trợ. SMTP mở rộng `8BITMIME` giúp client và server thương lượng khả năng xử lý nội dung 8-bit. Tuy nhiên, hỗ trợ 8BITMIME không đồng nghĩa mọi chặng, proxy và client luôn xử lý chính xác mọi dạng dữ liệu.

`binary` ít thông dụng hơn, vì việc truyền byte nhị phân không ràng buộc còn liên quan đến mở rộng SMTP như `BINARYMIME` và `CHUNKING`. Với email ứng dụng thông thường, hãy để Jakarta Mail chọn cách mã hóa MIME phù hợp thay vì tự cố gắng gửi dữ liệu nhị phân trực tiếp.

**`8BITMIME` và `SMTPUTF8` là hai khả năng khác nhau.** `8BITMIME` liên quan đến byte 8-bit của nội dung thông điệp trên đường SMTP; `SMTPUTF8` hỗ trợ trường hợp cần UTF-8 trong những thành phần email và địa chỉ quốc tế hóa mà SMTP truyền thống không cho phép. Một email có body tiếng Việt UTF-8 không nhất thiết đòi hỏi SMTPUTF8 nếu body đã được transfer-encode phù hợp và các thành phần khác không yêu cầu mở rộng này.

### 4.3. `quoted-printable`

Quoted-printable giữ phần lớn ASCII ở dạng dễ nhìn. Một byte cần mã hóa sẽ thành ký tự `=` cộng hai chữ số hexadecimal:

```text
Byte UTF-8:  C3 A0
QP:          =C3=A0
Ký tự:       à
```

Ví dụ đầy đủ:

```eml
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n
```

Sau khi giải mã quoted-printable, người đọc có các byte UTF-8 của `Chào bạn`; giải mã UTF-8 mới tạo lại chuỗi ký tự.

Trong quoted-printable:

- `=HH` biểu diễn một byte với giá trị hexadecimal `HH`.
- `=3D` biểu diễn byte của dấu `=` nếu cần escape.
- Một dấu `=` ở **cuối dòng được mã hóa** đánh dấu *soft line break*: dòng kế tiếp nối tiếp cùng nội dung mà không thêm xuống dòng logic.
- Việc mã hóa dấu cách hoặc tab ở cuối dòng cần tuân thủ quy tắc riêng để tránh bị mất do các hệ thống thư xử lý whitespace.
- Mỗi dòng mã hóa được giới hạn theo quy tắc của quoted-printable, thường tối đa 76 ký tự tính cả phần nội dung mã hóa, không tính CRLF.

Ví dụ soft line break chỉ để minh họa:

```text
Don hang cua ban =
da duoc xac nhan.
```

Sau khi giải mã, phần trên có ý nghĩa là một dòng `Don hang cua ban da duoc xac nhan.`.

Quoted-printable phù hợp khi nội dung phần lớn là ASCII và cần dễ đọc ở dạng raw message. Nếu phần lớn byte là ký tự đa byte cần escape, kích thước cũng có thể tăng đáng kể.

### 4.4. `base64`

Base64 biểu diễn byte bằng tập ký tự ASCII `A-Z`, `a-z`, `0-9`, `+`, `/` và dấu padding `=`. Nó thích hợp cho dữ liệu nhị phân và cũng có thể dùng cho văn bản.

Ví dụ đơn giản, nội dung byte của `Hello`:

```text
Original bytes (ASCII/UTF-8): 48 65 6C 6C 6F
Base64 representation:        SGVsbG8=
```

MIME part tương ứng:

```eml
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64

SGVsbG8=
```

Bên nhận giải mã base64 để có lại byte `48 65 6C 6C 6F`, rồi diễn giải chúng theo UTF-8 thành `Hello`.

Base64 **không phải mã hóa bảo mật**. Người nhận hoặc bất kỳ ai xem được raw message đều có thể khôi phục byte gốc. Độ dài dữ liệu base64 xấp xỉ `4/3` độ dài byte đầu vào, cộng thêm các ký tự xuống dòng khi chia dòng theo MIME. Trong MIME, dữ liệu base64 được chia thành các dòng không quá 76 ký tự.

Ví dụ với một PDF minh họa:

```eml
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKLi4u
```

Chuỗi base64 trên chỉ biểu diễn một vài byte đầu giả lập của nội dung PDF, **không phải một file PDF hoàn chỉnh**. Thư viện MIME cần encode toàn bộ byte thật của tệp đính kèm.

## 5. Cách ba yếu tố phối hợp và thứ tự xử lý

Với **text part**, thứ tự ở phía gửi là:

```text
Unicode String trong ứng dụng
        |
        | 1. Chọn Content-Type: text/plain hoặc text/html
        v
Ký tự văn bản
        |
        | 2. Charset: UTF-8
        v
Byte UTF-8
        |
        | 3. Content-Transfer-Encoding:
        |    quoted-printable / base64 / ...
        v
Biểu diễn phù hợp với SMTP
        |
        v
Đường truyền và hạ tầng lưu email
        |
        | 4. Giải mã transfer encoding
        v
Byte UTF-8
        |
        | 5. Giải mã charset
        v
Văn bản được mail client hiển thị
```

Đối với file nhị phân, không có bước biến byte PDF/PNG thành ký tự UTF-8. Hệ thống nhận chỉ giải mã transfer encoding để lấy lại **byte gốc của file**, rồi sử dụng `Content-Type` cùng phần mở rộng hoặc khả năng của client để mở file.

**Một lỗi phổ biến:** áp dụng base64 lên một Java String, rồi đưa chuỗi base64 đó vào `MimeMessageHelper.setText(...)` và tiếp tục ép MIME part thành `base64`. Điều này có thể gây **mã hóa hai lần**, khiến người nhận thấy chuỗi base64 hoặc dữ liệu sai. Hãy đưa **nội dung gốc** cho thư viện và để nó xử lý charset/transfer encoding.

### Một bảng ánh xạ dễ nhớ

| Câu hỏi | Thành phần trả lời | Ví dụ |
| --- | --- | --- |
| Dữ liệu là text, HTML, hình hay file? | `Content-Type` | `text/html` |
| Byte text giải ra chữ theo bảng mã nào? | `charset` của text part | `UTF-8` |
| Byte được biểu diễn an toàn trên đường email thế nào? | `Content-Transfer-Encoding` | `quoted-printable` |
| Tệp nên được trình bày như attachment hay inline? | `Content-Disposition` | `attachment; filename="a.pdf"` |
| Nhiều phần MIME được chia bằng gì? | `boundary` của `multipart` | `boundary="mix-123"` |

## 6. Một email có text, HTML và PDF đính kèm

Email thực tế thường có **nhiều tầng MIME lồng nhau**. Ví dụ sau thể hiện một thư có hai cách hiển thị cùng nội dung và một PDF:

```eml
MIME-Version: 1.0
From: billing@example.org
To: customer@example.net
Subject: Invoice
Content-Type: multipart/mixed; boundary="mixed-001"

--mixed-001
Content-Type: multipart/alternative; boundary="alt-001"

--alt-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n, vui l=C3=B2ng xem h=C3=B3a =C4=91=C6=A1n.

--alt-001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Ch=C3=A0o b=E1=BA=A1n, vui l=C3=B2ng xem <b>h=C3=B3a =C4=91=C6=A1n</b>.</p>

--alt-001--
--mixed-001
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQKLi4u

--mixed-001--
```

Giải thích:

1. Header ngoài cùng là `multipart/mixed` vì thư có phần nội dung chính và attachment.
2. Phần đầu là `multipart/alternative`: hai bản `text/plain` và `text/html` có cùng ý nghĩa.
3. Mỗi phiên bản text khai báo `charset=UTF-8` và `quoted-printable` riêng.
4. Phần PDF khai báo `application/pdf`, `base64` và `Content-Disposition: attachment`.
5. Hai boundary `mixed-001` và `alt-001` độc lập; mỗi cấu trúc có marker đóng bằng `--` ở cuối.

Các boundary và nội dung PDF trong ví dụ chỉ là minh họa. Khi tạo email thật, hãy để **Jakarta Mail/Spring MimeMessageHelper** sinh cấu trúc, boundary và chuyển mã cho từng phần.

### Vì sao không khai báo một charset chung cho toàn bộ thư?

Một thư `multipart` có thể chứa text UTF-8, một hình PNG và một file PDF. Charset chỉ có ý nghĩa đối với **phần văn bản**. Container `multipart` không thể dùng `charset=UTF-8` để biến tất cả child part thành text. Mỗi part mang thông tin định dạng phù hợp với chính dữ liệu của nó.

## 7. Spring Framework Mail: `JavaMailSender` và `MimeMessageHelper`

Với Spring, cách sử dụng phổ biến là:

```text
Business Service
       |
       v
JavaMailSender.createMimeMessage()
       |
       v
MimeMessageHelper
  - setText(...)
  - setSubject(...)
  - addAttachment(...)
       |
       v
Jakarta Mail tạo MIME entity + header + transfer encoding
       |
       v
JavaMailSender.send(mimeMessage)
       |
       v
SMTP server -> hệ thống nhận -> mail client
```

`JavaMailSender` là abstraction gửi mail của Spring Framework. `MimeMessage` và `MimeMessageHelper` thuộc cách sử dụng MIME cho những email phức tạp. `MimeMessageHelper` nhận charset khi khởi tạo và giúp cấu trúc multipart cũng như file đính kèm.

### 7.1. Dependency trong Spring Boot

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Một ví dụ `application.yml` dùng SMTP submission và cấu hình encoding mặc định:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
```

`spring.mail.default-encoding` là cấu hình mặc định do Spring Boot cung cấp cho thư gửi. Cần chọn cách kết nối SMTP và giá trị secret theo máy chủ thực tế. **Cấu hình này không thay thế việc khai báo đúng `Content-Type` khi tạo các phần MIME.**

Nếu dùng Spring Framework thuần, bạn cần tự cấu hình implementation `JavaMailSender`, Jakarta Mail và default encoding tương ứng.

### 7.2. Gửi HTML đúng Content-Type và UTF-8

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String to) throws MessagingException {
        MimeMessage mime = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mime, StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.org");
        helper.setTo(to);
        helper.setSubject("Chào mừng bạn đến với hệ thống");
        helper.setText(
                "<h1>Xin chào!</h1><p>Cảm ơn bạn đã đăng ký.</p>",
                true
        );

        mailSender.send(mime);
    }
}
```

Ở đây:

- Tham số `UTF-8` trong constructor của `MimeMessageHelper` yêu cầu helper dùng charset UTF-8 khi tạo các phần văn bản liên quan.
- `setText(html, true)` xác định body là **HTML**, dẫn đến `Content-Type: text/html` cho phần nội dung.
- `setSubject(...)` nhận Unicode String; Jakarta Mail chịu trách nhiệm mã hóa header thích hợp khi cần.
- Việc chọn `quoted-printable` hay `base64` cho transfer encoding có thể do Jakarta Mail quyết định theo dữ liệu và các thuộc tính liên quan. **Không nên giả định có một CTE cố định chỉ vì đã chọn UTF-8.**

Địa chỉ `notifications@example.org` chỉ là ví dụ; khi triển khai cần sử dụng một địa chỉ gửi được SMTP server cho phép.

### 7.3. Gửi cả text và HTML bằng `multipart/alternative`

Mail client có thể không hỗ trợ hoặc không muốn hiển thị HTML. Một email giao dịch thường có thêm bản text:

```java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, StandardCharsets.UTF_8.name()
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng");

String plain = "Chào bạn. Đơn hàng đã được xác nhận.";
String html = "<p>Chào bạn. <strong>Đơn hàng</strong> đã được xác nhận.</p>";

helper.setText(plain, html);
mailSender.send(mime);
```

Phương thức `setText(plainText, htmlText)` yêu cầu MIME multipart có hai lựa chọn thay thế cho cùng một thông điệp. Cấu trúc thực tế do helper và Jakarta Mail tạo, do đó không cần tự nối chuỗi `boundary`.

**Cả hai phiên bản phải truyền tải cùng thông tin nghiệp vụ.** Nếu bản HTML chứa một liên kết hành động quan trọng mà bản text bỏ qua hoàn toàn, người dùng chọn text-only có thể không thực hiện được thao tác cần thiết.

### 7.4. HTML, text và PDF đính kèm

Ví dụ tạo message có hai phiên bản văn bản và một PDF:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.charset.StandardCharsets;

public void sendInvoice(
        JavaMailSender mailSender,
        String recipient,
        byte[] invoicePdf
) throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("billing@example.org");
    helper.setTo(recipient);
    helper.setSubject("Hóa đơn của bạn");
    helper.setText(
            "Xin chào. Hóa đơn của bạn nằm trong tệp đính kèm.",
            "<p>Xin chào. <strong>Hóa đơn</strong> nằm trong tệp đính kèm.</p>"
    );
    helper.addAttachment(
            "hoa-don.pdf",
            new ByteArrayResource(invoicePdf),
            "application/pdf"
    );

    mailSender.send(message);
}
```

Ở ví dụ này:

- Phần văn bản được xử lý theo UTF-8.
- Text/HTML được nhóm thành các phiên bản thay thế.
- Phần PDF mang byte gốc từ `invoicePdf`; MIME layer sẽ mã hóa phần nhị phân để vận chuyển, thường là base64.
- Tên file và thông tin `Content-Type`/`Content-Disposition` được tạo bởi helper dựa trên lời gọi `addAttachment`.

`ByteArrayResource` thích hợp cho ví dụ khi byte PDF đã có sẵn trong bộ nhớ. Với tệp lớn, cân nhắc dùng `FileSystemResource` hoặc nguồn dữ liệu phù hợp để tránh giữ nhiều bản sao byte không cần thiết.

**Không biến `invoicePdf` thành Java String rồi gọi `setText(...)`.** Byte nhị phân của PDF cần được giữ nguyên như dữ liệu file.

## 8. Header Subject và tên attachment cũng có quy tắc mã hóa riêng

`charset=UTF-8` trên `Content-Type` chỉ khai báo charset của **body part tương ứng**, không tự động mô tả mọi trường header như `Subject` hoặc `filename`.

Trong MIME truyền thống, các giá trị header chứa ký tự không phải ASCII có thể cần cú pháp **encoded-word**, ví dụ:

```text
Subject: =?UTF-8?B?Q2jDoG8=?=
```

Chuỗi ví dụ là tiêu đề `Chào` được mã hóa theo dạng encoded-word. Ký hiệu `B` ở đây biểu thị base64 **dùng trong cú pháp mã hóa header**, không phải một header `Content-Transfer-Encoding: base64` của body. Encoded-word còn có biến thể `Q`, có liên quan tới quoted-printable nhưng quy tắc không hoàn toàn giống transfer encoding của body (chẳng hạn dấu gạch dưới có ý nghĩa đặc biệt trong `Q` encoded-word).

Tên tệp đính kèm chứa dấu như `hóa-đơn.pdf` là một trường hợp khác: giá trị parameter `filename` có thể được mã hóa theo các cơ chế dành cho tham số header MIME, chẳng hạn cách mở rộng trong RFC 2231. Khả năng hiển thị tên file còn phụ thuộc mail client.

Trong code Spring, hãy truyền Unicode String bình thường cho `setSubject(...)` và `addAttachment(filename, ...)` để thư viện thực hiện encoding phù hợp. **Không tự base64 toàn bộ subject rồi truyền trực tiếp làm subject**, vì dễ làm mail client hiển thị chuỗi vô nghĩa hoặc bị mã hóa lại.

## 9. Các lỗi hiển thị thường gặp và cách truy nguyên

| Triệu chứng ở người nhận | Khả năng nguyên nhân | Nên kiểm tra |
| --- | --- | --- |
| Thấy `ChÃ o` thay vì `Chào` | Byte UTF-8 bị diễn giải thành charset khác | `Content-Type` của đúng text part, byte sau giải mã CTE và nguồn tạo byte |
| Thấy `Ch=C3=A0o` nguyên văn | Quoted-printable không được nhận diện/giải mã như mong đợi | `Content-Transfer-Encoding` và MIME part chứa body |
| Thấy `SGVsbG8=` thay vì `Hello` | Base64 được coi như text gốc hoặc encoded hai lần | Header CTE, cách ứng dụng chuẩn bị payload |
| HTML hiện nguyên tag `<p>`, `<strong>` | Đã khai báo `text/plain` hoặc gọi `setText(html, false)` | Media type và tham số `isHtml` |
| Chữ có dấu hiện thành `?` | Ký tự bị mất trong quá trình encode bằng charset không hỗ trợ | Charset từ nguồn, chuyển đổi byte và MIME charset |
| Attachment mở ra báo hỏng file | Byte gốc bị thay đổi, transfer encoding sai hoặc file nguồn đã lỗi | Kích thước/file gốc, MIME part và quá trình decode |
| Attachment bị hiển thị như chữ dài | Phần file có sai `Content-Type`/`Content-Disposition` hoặc bị đặt nhầm vào text body | Dùng `addAttachment` và xem header part |
| Tên file đính kèm mất dấu | Parameter `filename` được encode không tương thích hoặc giải mã sai | Thư viện tạo attachment, mail client và raw MIME headers |
| Chỉ nhìn thấy một phần HTML hoặc bị lỗi layout | MIME multipart/alternative/related sai hoặc HTML không được client hỗ trợ | Cấu trúc MIME và tính tương thích HTML email |
| Mail client không tách được các part | Boundary bị đặt sai, thiếu marker đóng hoặc sửa thủ công | `Content-Type: multipart` cùng các delimiter |

### 9.1. Kiểm tra đúng MIME part

Với email đơn giản, có thể chỉ có một `Content-Type` ngoài cùng. Nhưng với thư có attachment, header ngoài cùng thường là `multipart/*`, còn `charset=UTF-8` nằm trên các **text part bên trong**. Nếu chỉ nhìn header ngoài cùng rồi kết luận “email không có UTF-8”, rất dễ chẩn đoán sai.

Một cách đọc raw message có hệ thống:

1. Xem header ngoài cùng: `MIME-Version` và `Content-Type`.
2. Nếu là multipart, đọc `boundary` và tìm từng MIME part.
3. Với mỗi part, xác định `Content-Type` và parameter `charset` nếu đó là văn bản.
4. Kiểm tra `Content-Transfer-Encoding` của **chính part đó**.
5. Giải mã CTE thành byte, rồi áp dụng charset để diễn giải byte văn bản.
6. Nếu là attachment, so sánh byte sau decode với nguồn gốc của tệp.

Không cần biết mật khẩu SMTP để kiểm tra ba header MIME: chúng là thông tin của **thông điệp**, không phải thông tin xác thực gửi mail.

### 9.2. Vì sao set charset đúng vẫn có thể lỗi?

Ví dụ ứng dụng đọc file template có byte UTF-8 nhưng lại dùng một API đã mặc định giải mã file thành `ISO-8859-1`. Khi đó, Java `String` đã chứa ký tự sai *trước lúc* được đưa vào `MimeMessageHelper`. Cấu hình `UTF-8` cho email chỉ giúp mã hóa **chuỗi sai đó** một cách nhất quán; không thể khôi phục văn bản gốc.

Do đó, cần xét toàn bộ đường đi:

```text
File template / Database / API
         |
         | Đọc nguồn với đúng charset
         v
Java String đúng nội dung
         |
         | MimeMessageHelper UTF-8
         v
MIME bytes + CTE
         |
         v
Mail client
```

Lỗi sai ký tự có thể nằm ở **nguồn dữ liệu**, **bước chuyển charset**, **khai báo MIME** hoặc **giải mã phía client**.

### 9.3. Không chỉnh MIME bằng cách thay thế chuỗi trên raw message

Các thao tác như thay tất cả `Content-Type: text/plain` thành `text/html`, đổi `boundary` bằng tìm-kiếm/thay-thế, hoặc sửa `quoted-printable` sau khi thư viện đã đóng gói có thể làm toàn bộ message không nhất quán. Thay vì sửa raw MIME bằng text replacement, hãy đặt đúng nội dung qua các phương thức của `MimeMessageHelper`.

## 10. Một số chi tiết giao thức thường bị nhầm

### 10.1. MIME encoding không phải SMTP dot-stuffing

Trong SMTP truyền thống, khi client gửi nội dung sau lệnh `DATA`, một dòng chỉ có dấu chấm `.` dùng để đánh dấu kết thúc dữ liệu; các dòng bắt đầu bằng dấu chấm được xử lý theo cơ chế **dot-stuffing** để không bị hiểu nhầm là kết thúc message.

Đây là quy tắc **framing của SMTP**, khác với `Content-Transfer-Encoding` của MIME part. Thư viện SMTP thường tự xử lý dot-stuffing; ứng dụng không nên tự chèn dấu chấm khi tạo văn bản nội dung.

### 10.2. `Content-Transfer-Encoding` không phải `Content-Encoding` của HTTP

HTTP có khái niệm như `Content-Encoding: gzip` để biểu thị một phép biến đổi biểu diễn dữ liệu. Trong MIME email, `Content-Transfer-Encoding` giải quyết khả năng vận chuyển byte qua đường truyền thư, thường bằng base64 hoặc quoted-printable.

Tên gần giống không làm cho chúng tương đương. `base64` cũng không phải gzip và không cung cấp tính bảo mật.

### 10.3. HTML email không luôn giống HTML trên web

`Content-Type: text/html` chỉ cho mail client biết phần đó là HTML. Mail client có thể bỏ script, thay đổi CSS, không tải hình từ xa hoặc chuyển sang bản text. Không có header MIME nào buộc tất cả client hiển thị email y hệt trình duyệt.

### 10.4. MIME encoding có thể do thư viện tự chọn

Hai email cùng có `Content-Type: text/plain; charset=UTF-8` có thể lần lượt dùng `quoted-printable` và `base64`. Cả hai đều hợp lệ nếu nội dung được mã và giải mã theo đúng header. Hãy dựa vào **ngữ nghĩa dữ liệu khôi phục được**, thay vì coi một biểu diễn thô cụ thể là bắt buộc.

## 11. Các tình huống vận dụng

### Tình huống A: Email tiếng Việt hiện “ChÃ o”

Ứng dụng gửi chuỗi `Chào bạn` nhưng người nhận thấy `ChÃ o báº¡n`.

**Phân tích:** cần kiểm tra nguồn tạo chuỗi, byte được tạo ở bước charset, header `Content-Type` của text part và cách client giải mã. `Content-Transfer-Encoding` có thể hoàn toàn hợp lệ; lỗi xảy ra vì byte UTF-8 được hiểu bằng bộ mã khác.

### Tình huống B: Khai báo `UTF-8` nhưng body có `=E1=BA=AD`

Xem raw message thấy `Content-Type: text/plain; charset=UTF-8`, `Content-Transfer-Encoding: quoted-printable` và nhiều chuỗi `=HH`.

**Phân tích:** đây có thể là dữ liệu hoàn toàn đúng chuẩn. Quoted-printable được thiết kế để biểu diễn byte theo cách đó. Mail client giải mã CTE trước rồi mới giải mã UTF-8.

### Tình huống C: Email HTML hiển thị tag dưới dạng text

Service gọi `helper.setText("<h1>Xin chào</h1>", false)`.

**Phân tích:** tham số `false` khai báo nội dung là text thuần. Muốn nội dung là HTML, dùng `helper.setText(html, true)`. Với nhu cầu hỗ trợ cả hai kiểu hiển thị, dùng `helper.setText(plain, html)`.

### Tình huống D: File PDF không mở được

Một service chuyển `byte[]` của PDF thành `new String(pdfBytes, UTF_8)` rồi truyền như body của thư.

**Phân tích:** byte PDF không phải văn bản UTF-8. Việc ép decode thành Java String có thể làm mất byte không hợp lệ. Hãy giữ byte gốc và gọi `helper.addAttachment("invoice.pdf", new ByteArrayResource(pdfBytes), "application/pdf")`.

### Tình huống E: Chỉ thay `Content-Type` ngoài cùng không giúp sửa chữ có dấu

Message có `Content-Type: multipart/mixed`, bên trong text part khai báo sai `charset=US-ASCII`.

**Phân tích:** charset cần được kiểm tra và khai báo ở **text part thực sự**, không phải dùng một charset chung để xử lý cả container và attachment.

### Tình huống F: Subject có dấu nhưng body bình thường

Phần body được khai báo `text/plain; charset=UTF-8` và hiển thị đúng; chỉ có `Subject` bị sai.

**Phân tích:** subject thuộc **message header**, dùng quy tắc mã hóa header riêng; `Content-Type` và CTE của body không trực tiếp mã hóa subject. Để Jakarta Mail xử lý tiêu đề Unicode qua `MimeMessageHelper.setSubject(...)`.

## 12. Những nguyên tắc cần ghi nhớ khi viết Spring Mail

1. **Xác định đúng media type:** text thuần dùng `text/plain`; HTML dùng `text/html`; PDF dùng `application/pdf`.
2. **Dùng UTF-8 cho văn bản tiếng Việt:** cấu hình default encoding khi cần và truyền UTF-8 vào `MimeMessageHelper`.
3. **Tách charset khỏi transfer encoding:** charset quyết định **ký tự ↔ byte**; CTE quyết định **byte ↔ dạng biểu diễn trên đường email**.
4. **Không tự mã hóa lại dữ liệu đã đưa cho Jakarta Mail:** thông thường nên đưa nội dung và attachment gốc cho helper.
5. **Đọc theo từng MIME part:** thông tin của container multipart không thay thế header của text/attachment part bên trong.
6. **Chọn API đúng:** `setText(text, false)` cho text, `setText(html, true)` cho HTML, `setText(plain, html)` cho hai phiên bản, `addAttachment(...)` cho file.
7. **Dùng raw MIME để chẩn đoán:** xem `Content-Type`, `charset`, `Content-Transfer-Encoding`, `boundary` và cấu trúc part; không kết luận chỉ từ chuỗi đang hiện trong log.

Trong một email đúng định dạng, **`Content-Type` mô tả ý nghĩa của phần nội dung, `charset` diễn giải byte của văn bản, còn `Content-Transfer-Encoding` giúp các byte đi qua hạ tầng thư an toàn**. Ba lớp này phối hợp với nhau, và `MimeMessageHelper` giúp ứng dụng Spring tạo ra chúng mà không phải tự ghép raw MIME bằng tay.
