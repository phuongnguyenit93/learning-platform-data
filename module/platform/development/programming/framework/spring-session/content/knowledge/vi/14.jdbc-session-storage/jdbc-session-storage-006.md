# PRIMARY_ID, SESSION_ID và ý nghĩa của từng định danh

Trong Spring Session JDBC, một phiên thường được biểu diễn bằng hai định danh khác nhau trong bảng **SPRING_SESSION**: **PRIMARY_ID** và **SESSION_ID**. Hai cột này không trùng vai trò. **PRIMARY_ID** là khóa chính nội bộ của bản ghi phiên trong cơ sở dữ liệu; **SESSION_ID** là định danh phiên mà client gửi trong cookie hoặc HTTP header để server tìm lại phiên ở request tiếp theo.

Việc tách hai định danh giúp Spring Session duy trì quan hệ dữ liệu ổn định trong JDBC, đặc biệt khi session ID được thay đổi sau xác thực để bảo vệ khỏi session fixation. Nếu hiểu nhầm hai cột, ứng dụng có thể thiết kế sai khóa ngoại, truy vấn nhầm bản ghi, làm hỏng liên kết thuộc tính phiên hoặc vô tình để lộ định danh nội bộ.

Bài học tập trung vào **JdbcIndexedSessionRepository** và schema JDBC tiêu chuẩn của Spring Session. Tên bảng, kiểu dữ liệu và câu SQL có thể được tùy chỉnh theo hệ quản trị cơ sở dữ liệu và phiên bản, nhưng sự khác nhau về vai trò giữa khóa chính nội bộ và session ID vẫn là nguyên tắc cần nắm.

## 1. Hai định danh giải quyết hai nhu cầu khác nhau

Một request HTTP cần mang theo một giá trị để server nhận biết phiên của client. Trong cấu hình cookie, trình duyệt gửi session ID trong cookie; với resolver dùng header, client gửi ID trong header. Spring Session lấy giá trị đó và tìm bản ghi phiên trong repository.

Ở phía JDBC, cơ sở dữ liệu cũng cần một khóa ổn định để nhận diện bản ghi phiên và liên kết các bảng con. Đó là vai trò của **PRIMARY_ID**.

| Định danh | Vai trò chính | Nơi sử dụng | Có được gửi cho client? |
|---|---|---|---|
| **PRIMARY_ID** | Khóa chính nội bộ của một bản ghi phiên trong JDBC | Khóa chính bảng **SPRING_SESSION**, khóa ngoại từ bảng thuộc tính | Không |
| **SESSION_ID** | Định danh phiên trong giao thức trao đổi giữa client và server | Cookie/header và điều kiện tìm phiên trong repository | Có, dưới dạng credential cần bảo vệ |
| User ID / principal name | Danh tính người dùng hoặc tài khoản trong nghiệp vụ | Spring Security, truy vấn phiên theo principal, nghiệp vụ tài khoản | Không thay thế hai ID trên |

Có thể hình dung:

    Client
      |
      | Cookie / Header chứa SESSION_ID
      v
    Spring Session
      |
      | Tìm bản ghi theo SESSION_ID
      v
    SPRING_SESSION
      |
      | PRIMARY_ID
      v
    SPRING_SESSION_ATTRIBUTES

**SESSION_ID** giúp định vị phiên từ request. Sau khi tìm được bản ghi, **PRIMARY_ID** giúp cơ sở dữ liệu liên kết bản ghi phiên với các thuộc tính được lưu trong bảng con.

## 2. SESSION_ID: định danh trao đổi với client

**SESSION_ID** là giá trị đại diện cho phiên trong các request HTTP. Client nhận ID từ response, thường qua cookie **SESSION** hoặc header do **HttpSessionIdResolver** cấu hình, rồi gửi lại ở các request tiếp theo.

Ví dụ request dùng cookie:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: SESSION=<session-id>
~~~

Ví dụ request dùng header:

~~~http
GET /account HTTP/1.1
Host: api.example.test
X-Auth-Token: <session-id>
~~~

Giá trị **<session-id>** là placeholder. ID thực tế do Spring Session tạo và quản lý. Khi repository nhận request, nó dùng session ID để tìm phiên tương ứng.

Những đặc điểm cần nhớ:

- Session ID gắn với một phiên cụ thể, không phải tài khoản người dùng.
- Một principal có thể có nhiều session ID trên nhiều thiết bị.
- Session ID có thể được thay đổi theo chính sách bảo vệ session fixation.
- Khi phiên bị invalidate hoặc hết hạn, ID cũ không còn được dùng để khôi phục phiên hợp lệ.
- Session ID là thông tin nhạy cảm; người có ID còn hiệu lực có thể chiếm quyền sử dụng phiên.

Không đưa session ID vào URL, log, mã theo dõi hoặc thông báo lỗi. Khi kiểm tra request, chỉ cần xác nhận header/cookie có được gửi và server có khôi phục được phiên, không cần in toàn bộ giá trị ID.

## 3. PRIMARY_ID: khóa chính nội bộ của bản ghi JDBC

Trong schema tiêu chuẩn, **PRIMARY_ID** là khóa chính của bảng **SPRING_SESSION**. Cột này được dùng để nhận diện ổn định một hàng trong cơ sở dữ liệu và làm đích tham chiếu cho các bản ghi thuộc tính phiên.

Ví dụ cấu trúc khái quát:

~~~sql
CREATE TABLE SPRING_SESSION (
    PRIMARY_ID CHAR(36) NOT NULL,
    SESSION_ID CHAR(36) NOT NULL,
    CREATION_TIME BIGINT NOT NULL,
    LAST_ACCESS_TIME BIGINT NOT NULL,
    MAX_INACTIVE_INTERVAL INT NOT NULL,
    EXPIRY_TIME BIGINT NOT NULL,
    PRINCIPAL_NAME VARCHAR(100),
    CONSTRAINT SPRING_SESSION_PK PRIMARY KEY (PRIMARY_ID)
);
~~~

Trong schema tiêu chuẩn, **PRIMARY_ID** thường có dạng UUID được lưu dưới dạng chuỗi 36 ký tự. Nó là định danh lưu trữ do Spring Session quản lý, không phải số tự tăng hoặc ID tài khoản. Schema tùy chỉnh có thể dùng kiểu dữ liệu khác nếu repository và câu SQL được cấu hình tương ứng.

Vai trò của **PRIMARY_ID**:

1. Xác định duy nhất một hàng phiên trong **SPRING_SESSION**.
2. Làm khóa tham chiếu từ bảng **SPRING_SESSION_ATTRIBUTES**.
3. Giữ quan hệ giữa phiên và thuộc tính ổn định khi **SESSION_ID** thay đổi.
4. Cho phép repository cập nhật hoặc xóa dữ liệu phiên theo định danh lưu trữ nội bộ.

Ứng dụng nghiệp vụ thông thường không cần biết **PRIMARY_ID**. Khi làm việc qua **HttpSession**, **SessionRepository** hoặc Spring Security, code sử dụng session ID và API tương ứng. Không nên tự truy vấn **PRIMARY_ID** rồi gửi giá trị đó cho client.

## 4. Quan hệ giữa hai bảng JDBC

Spring Session JDBC tiêu chuẩn thường lưu metadata phiên trong **SPRING_SESSION** và các thuộc tính trong **SPRING_SESSION_ATTRIBUTES**.

Bảng thuộc tính có cấu trúc khái quát:

~~~sql
CREATE TABLE SPRING_SESSION_ATTRIBUTES (
    SESSION_PRIMARY_ID CHAR(36) NOT NULL,
    ATTRIBUTE_NAME VARCHAR(200) NOT NULL,
    ATTRIBUTE_BYTES BLOB NOT NULL,
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_PK
        PRIMARY KEY (SESSION_PRIMARY_ID, ATTRIBUTE_NAME),
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_FK
        FOREIGN KEY (SESSION_PRIMARY_ID)
        REFERENCES SPRING_SESSION(PRIMARY_ID)
        ON DELETE CASCADE
);
~~~

Kiểu **BLOB** trong ví dụ phù hợp với một số hệ quản trị; PostgreSQL thường dùng **BYTEA**. Hãy dùng schema script đi kèm đúng module và dialect của dự án. Không sao chép nguyên kiểu dữ liệu từ ví dụ sang mọi database.

Quan hệ chính:

- **SPRING_SESSION.PRIMARY_ID** là khóa chính của phiên.
- **SPRING_SESSION_ATTRIBUTES.SESSION_PRIMARY_ID** là khóa ngoại trỏ đến **PRIMARY_ID**.
- Một phiên có thể có nhiều thuộc tính, mỗi thuộc tính được nhận diện bằng cặp **SESSION_PRIMARY_ID** và **ATTRIBUTE_NAME**.
- Khi hàng phiên bị xóa, **ON DELETE CASCADE** trong schema tương ứng có thể xóa các hàng thuộc tính liên quan.

Vì khóa ngoại tham chiếu **PRIMARY_ID**, các hàng thuộc tính không cần tham chiếu trực tiếp **SESSION_ID**. Đây là điểm quan trọng khi session ID được xoay vòng: quan hệ giữa bản ghi phiên và các thuộc tính vẫn dựa trên khóa chính nội bộ.

## 5. Vì sao không dùng SESSION_ID làm khóa chính?

Thoạt nhìn, dùng **SESSION_ID** làm khóa chính có vẻ đơn giản vì client đã gửi giá trị này trong mọi request. Nhưng session ID có thể được thay đổi trong vòng đời phiên, chẳng hạn sau khi người dùng đăng nhập thành công.

Nếu khóa chính đồng thời là ID được thay đổi, việc xoay vòng ID có thể kéo theo cập nhật khóa ngoại trong bảng thuộc tính và các bảng phụ. Điều này làm quan hệ dữ liệu phức tạp hơn và tăng rủi ro cập nhật không đồng bộ.

Tách **PRIMARY_ID** và **SESSION_ID** giải quyết vấn đề:

- **PRIMARY_ID** giữ ổn định quan hệ nội bộ trong database.
- **SESSION_ID** có thể được thay thế khi cần đổi định danh phía client.
- Bảng thuộc tính tiếp tục tham chiếu cùng **PRIMARY_ID**.
- Các truy vấn từ client vẫn dùng **SESSION_ID**, không cần biết khóa chính nội bộ.

Ví dụ trước khi đổi session ID:

| Cột | Giá trị minh họa |
|---|---|
| **PRIMARY_ID** | **p-7f21...** |
| **SESSION_ID** | **s-a111...** |

Sau khi Spring Security yêu cầu đổi session ID:

| Cột | Giá trị minh họa |
|---|---|
| **PRIMARY_ID** | **p-7f21...** |
| **SESSION_ID** | **s-b222...** |

**PRIMARY_ID** không đổi trong cùng vòng đời bản ghi; **SESSION_ID** được thay bằng giá trị mới. Bản ghi thuộc tính vẫn liên kết với **p-7f21...**.

Các giá trị trên chỉ minh họa quan hệ, không phải format ID cố định mà ứng dụng nên tự tạo.

## 6. Quy trình tạo phiên và lưu thuộc tính

Khi ứng dụng tạo một phiên mới, Spring Session JDBC cần tạo định danh cho bản ghi nội bộ và session ID. Repository lưu metadata phiên vào **SPRING_SESSION**, sau đó lưu các thuộc tính vào **SPRING_SESSION_ATTRIBUTES** gắn với **PRIMARY_ID**.

Luồng khái quát:

1. Controller hoặc Spring Security gọi **request.getSession()** và tạo phiên mới.
2. Spring Session tạo **SESSION_ID** để client có thể nhận diện phiên.
3. Repository có **PRIMARY_ID** để nhận diện hàng phiên trong JDBC.
4. Metadata được lưu vào **SPRING_SESSION**.
5. Các thuộc tính như **cart**, **locale** hoặc **SPRING_SECURITY_CONTEXT** được serialize và lưu vào **SPRING_SESSION_ATTRIBUTES**.
6. **SESSION_PRIMARY_ID** của từng thuộc tính nhận giá trị **PRIMARY_ID** của hàng cha.
7. Response gửi **SESSION_ID** cho client qua cookie hoặc header.

Ví dụ controller không cần biết hai định danh nội bộ:

~~~java
@PostMapping("/cart")
public ResponseEntity<Void> saveCart(HttpServletRequest request) {
    HttpSession session = request.getSession();
    session.setAttribute("cartCount", 3);

    return ResponseEntity.noContent().build();
}
~~~

Controller chỉ thao tác với **HttpSession**. Spring Session đảm nhiệm việc lưu metadata, ID và thuộc tính theo schema JDBC. Không tự tạo **PRIMARY_ID** hoặc ghi hai bảng bằng JDBC trong controller.

## 7. Quy trình tìm phiên từ một request

Khi client gửi lại **SESSION_ID**, Spring Session dùng ID đó để tìm bản ghi tương ứng. Ở mức khái niệm, quá trình gồm:

1. **HttpSessionIdResolver** đọc session ID từ cookie hoặc header.
2. **SessionRepositoryFilter** chuyển ID cho repository.
3. JDBC repository tìm hàng trong **SPRING_SESSION** theo **SESSION_ID**.
4. Từ hàng tìm được, repository có **PRIMARY_ID**.
5. Repository dùng **PRIMARY_ID** để tải các hàng thuộc tính từ **SPRING_SESSION_ATTRIBUTES**.
6. Các byte thuộc tính được deserialize thành object trong JVM.
7. Ứng dụng tiếp tục xử lý request với **HttpSession** đã khôi phục.

Ví dụ truy vấn minh họa:

~~~sql
SELECT PRIMARY_ID, SESSION_ID, CREATION_TIME,
       LAST_ACCESS_TIME, MAX_INACTIVE_INTERVAL,
       EXPIRY_TIME, PRINCIPAL_NAME
FROM SPRING_SESSION
WHERE SESSION_ID = ?;
~~~

Sau khi có **PRIMARY_ID**, repository có thể tải thuộc tính:

~~~sql
SELECT ATTRIBUTE_NAME, ATTRIBUTE_BYTES
FROM SPRING_SESSION_ATTRIBUTES
WHERE SESSION_PRIMARY_ID = ?;
~~~

Đây là SQL minh họa để giải thích quan hệ dữ liệu. Câu truy vấn thực tế, cách cập nhật last access time, xử lý hết hạn và chiến lược batch phụ thuộc repository và phiên bản. Không nên tự thay câu SQL nội bộ của repository nếu chưa hiểu hợp đồng của implementation.

## 8. Điều gì xảy ra khi session ID được thay đổi?

Spring Security có các chiến lược bảo vệ session fixation. Sau xác thực thành công, một chiến lược có thể yêu cầu thay đổi session ID để kẻ tấn công không thể tiếp tục sử dụng ID đã biết trước khi đăng nhập.

Với Spring Session JDBC, thao tác này liên quan đến **SESSION_ID**. Repository cập nhật ID trao đổi với client trên hàng phiên hiện tại. **PRIMARY_ID** vẫn là khóa chính nội bộ, do đó các hàng thuộc tính tiếp tục tham chiếu cùng bản ghi cha.

Luồng khái quát:

    Trước xác thực:
      PRIMARY_ID = P-1
      SESSION_ID = S-OLD
      ATTRIBUTES -> SESSION_PRIMARY_ID = P-1

    Sau khi đổi session ID:
      PRIMARY_ID = P-1
      SESSION_ID = S-NEW
      ATTRIBUTES -> SESSION_PRIMARY_ID = P-1

Client cần nhận ID mới trong response và thay thế ID cũ. Request tiếp theo gửi **S-NEW**; repository tìm hàng theo **SESSION_ID** mới, sau đó tải thuộc tính theo **PRIMARY_ID** hiện tại.

Không tự thay **SESSION_ID** bằng SQL trong khi ứng dụng đang hoạt động. Thao tác trực tiếp có thể không cập nhật response cookie/header, cache nội bộ, sự kiện hoặc các cấu trúc phụ trợ khác. Hãy để Spring Security và Spring Session thực hiện đổi ID qua API được hỗ trợ.

## 9. Xóa phiên và xóa thuộc tính liên quan

Khi người dùng logout hoặc ứng dụng gọi **session.invalidate()**, repository cần xóa phiên. Về mặt dữ liệu quan hệ, việc xóa hàng cha trong **SPRING_SESSION** phải xử lý các hàng thuộc tính con.

Nếu schema có khóa ngoại **ON DELETE CASCADE**, database xóa các hàng **SPRING_SESSION_ATTRIBUTES** tham chiếu **PRIMARY_ID** tương ứng. Nếu schema tùy chỉnh không có cascade, câu lệnh hoặc quy trình xóa phải xử lý bảng con trước hoặc theo đúng chiến lược repository hỗ trợ.

Điều cần kiểm tra:

- Khóa ngoại trỏ đến đúng **SPRING_SESSION.PRIMARY_ID**.
- Kiểu dữ liệu của **SESSION_PRIMARY_ID** tương thích với **PRIMARY_ID**.
- Tên bảng/cột khớp với SQL schema được repository sử dụng.
- Xóa phiên qua repository làm mất cả metadata lẫn thuộc tính.
- Bản ghi phiên hết hạn được dọn theo tác vụ cleanup tương ứng.

Không xóa riêng hàng **SPRING_SESSION** bằng SQL tùy tiện rồi bỏ lại thuộc tính mồ côi nếu database không có cascade. Ngược lại, cũng không xóa bảng **SPRING_SESSION_ATTRIBUTES** theo **SESSION_ID**, vì bảng con liên kết bằng **SESSION_PRIMARY_ID**.

## 10. Các ràng buộc và chỉ mục quan trọng

Schema JDBC tiêu chuẩn dùng các ràng buộc để bảo vệ quan hệ giữa hai định danh:

| Ràng buộc / chỉ mục | Mục đích |
|---|---|
| Primary key trên **PRIMARY_ID** | Bảo đảm mỗi hàng phiên có khóa nội bộ duy nhất |
| Unique constraint/index trên **SESSION_ID** | Không cho hai hàng phiên dùng cùng một ID client |
| Index trên **EXPIRY_TIME** | Hỗ trợ tìm và dọn phiên hết hạn |
| Index trên **PRINCIPAL_NAME** (nếu schema hỗ trợ) | Hỗ trợ truy vấn phiên theo principal |
| Primary key trên (**SESSION_PRIMARY_ID**, **ATTRIBUTE_NAME**) | Mỗi tên thuộc tính chỉ có một hàng trong một phiên |
| Foreign key từ **SESSION_PRIMARY_ID** đến **PRIMARY_ID** | Bảo đảm thuộc tính thuộc về một hàng phiên hợp lệ |

**SESSION_ID** cần unique vì repository tìm phiên từ giá trị client gửi. Nếu có hai hàng cùng **SESSION_ID**, truy vấn không còn xác định được một phiên duy nhất và có thể dẫn đến lỗi dữ liệu hoặc hành vi không dự đoán.

**PRIMARY_ID** cần là khóa chính vì mọi hàng thuộc tính dựa vào nó. Không nên loại bỏ hoặc thay đổi ràng buộc này chỉ vì ứng dụng không truy vấn trực tiếp cột đó.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
|---|---|---|
| Cho rằng **PRIMARY_ID** chính là cookie session ID | Ứng dụng có thể gửi nhầm khóa nội bộ ra client | Client trao đổi **SESSION_ID** |
| Cho rằng **SESSION_ID** là khóa chính của bảng | Thiết kế khóa ngoại và ID rotation dễ bị sai | **PRIMARY_ID** là PK; **SESSION_ID** thường có unique constraint |
| Dùng user ID thay cho **SESSION_ID** | Nhiều phiên của cùng người dùng bị nhập làm một | Một user có thể có nhiều session ID |
| Liên kết bảng thuộc tính bằng **SESSION_ID** | Đổi session ID có thể làm phức tạp hoặc phá liên kết | **SESSION_PRIMARY_ID** tham chiếu **PRIMARY_ID** |
| Tự sửa hai ID bằng SQL | Có thể bỏ qua logic repository và cập nhật response | Dùng API Spring Session/Spring Security |
| Xóa hàng cha mà không xử lý hàng con | Có thể để lại thuộc tính mồ côi nếu không có cascade | Giữ đúng foreign key và chính sách xóa |
| Ghi **PRIMARY_ID** vào log hoặc API | Làm lộ chi tiết nội bộ và tăng phụ thuộc schema | Giữ ID nội bộ trong tầng lưu trữ |

Một điểm quan trọng nữa: **PRIMARY_ID** không phải khóa bí mật xác thực. Nhưng việc nó không được gửi cho client không có nghĩa có thể tùy tiện công khai trong log hoặc API. Giữ nó trong phạm vi persistence giúp giảm phụ thuộc và tránh làm lộ chi tiết nội bộ.

## 12. Tùy chỉnh schema và migration

Spring Session cung cấp schema script theo các hệ quản trị cơ sở dữ liệu được hỗ trợ. Khi dùng schema mặc định, hãy khởi tạo đúng script của dialect đang chạy. Nếu tổ chức cần đổi tên bảng, đổi kiểu dữ liệu hoặc thêm ràng buộc, phải bảo đảm câu SQL của repository được tùy chỉnh tương ứng.

Khi migration schema:

- Giữ **PRIMARY_ID** là khóa chính ổn định.
- Giữ **SESSION_ID** unique để repository tìm phiên không mơ hồ.
- Giữ khóa ngoại từ **SESSION_PRIMARY_ID** đến **PRIMARY_ID**.
- Bảo đảm kiểu dữ liệu hai phía của khóa ngoại tương thích.
- Giữ các index cần thiết cho expiry và principal lookup.
- Kiểm tra **ON DELETE CASCADE** hoặc cơ chế xóa thuộc tính tương đương.
- Thực hiện migration trên bản sao dữ liệu trước khi áp dụng production.
- Kiểm tra rollback nếu thay đổi kiểu cột hoặc tên cột.

Không đổi tên **PRIMARY_ID** hoặc **SESSION_ID** chỉ để đồng nhất với quy ước nội bộ của ứng dụng mà không cập nhật SQL repository. Tên cột là một phần của hợp đồng giữa repository và schema. Nếu cần schema riêng, hãy dùng cơ chế tùy chỉnh được Spring Session hỗ trợ và kiểm thử với đúng database.

## 13. Chẩn đoán lỗi dựa trên hai định danh

Khi session không khôi phục được, hãy xác định lỗi nằm ở bước tìm phiên hay bước tải thuộc tính.

| Triệu chứng | Khu vực cần kiểm tra |
|---|---|
| Request gửi cookie/header nhưng repository không tìm thấy phiên | Giá trị **SESSION_ID**, cookie path/domain, resolver và hàng **SPRING_SESSION** |
| Truy vấn theo **SESSION_ID** không trả về hàng | Phiên đã hết hạn/xóa, ID sai hoặc dữ liệu bị mất |
| Hàng phiên tồn tại nhưng không tải được thuộc tính | **PRIMARY_ID**, khóa ngoại và bảng **SPRING_SESSION_ATTRIBUTES** |
| Vi phạm unique constraint khi ghi phiên | **SESSION_ID** trùng hoặc dữ liệu cạnh tranh/cũ chưa được dọn đúng |
| Vi phạm foreign key khi lưu thuộc tính | **SESSION_PRIMARY_ID** không trỏ đến **PRIMARY_ID** hiện có |
| Đổi session ID xong request tiếp theo mất phiên | Client chưa nhận/gửi ID mới hoặc thao tác đổi ID không hoàn tất |
| Xóa phiên nhưng còn hàng thuộc tính | Thiếu cascade hoặc quy trình cleanup không xóa bảng con |

Có thể dùng truy vấn chỉ đọc để kiểm tra quan hệ:

~~~sql
SELECT PRIMARY_ID, SESSION_ID, EXPIRY_TIME
FROM SPRING_SESSION
WHERE SESSION_ID = ?;
~~~

Sau đó dùng **PRIMARY_ID** vừa tìm được:

~~~sql
SELECT SESSION_PRIMARY_ID, ATTRIBUTE_NAME
FROM SPRING_SESSION_ATTRIBUTES
WHERE SESSION_PRIMARY_ID = ?;
~~~

Trong production, các truy vấn chẩn đoán cần được giới hạn quyền, tránh chọn hoặc in **ATTRIBUTE_BYTES** vì dữ liệu đó có thể chứa SecurityContext và thông tin nhạy cảm. Không đưa session ID đầy đủ vào ticket hoặc log; dùng mã đã che hoặc hash khi cần đối chiếu.

## 14. Kiểm thử hành vi của PRIMARY_ID và SESSION_ID

Nên kiểm thử với database thật hoặc môi trường tích hợp tương thích với dialect production. Mock repository không xác minh được ràng buộc, khóa ngoại và câu SQL thực tế.

Các trường hợp nên có:

1. Tạo một phiên qua **HttpSession**, xác nhận có hàng trong **SPRING_SESSION**.
2. Xác nhận **PRIMARY_ID** là duy nhất và **SESSION_ID** có unique constraint.
3. Ghi một thuộc tính phiên, xác nhận hàng thuộc tính tham chiếu **PRIMARY_ID** của hàng cha.
4. Gửi request tiếp theo với **SESSION_ID**, xác nhận repository tìm đúng phiên và tải được thuộc tính.
5. Đổi session ID sau xác thực, xác nhận **SESSION_ID** thay đổi còn **PRIMARY_ID** và liên kết thuộc tính vẫn ổn định.
6. Gửi ID cũ sau khi đổi, xác nhận ID cũ không còn khôi phục phiên.
7. Invalidate phiên, xác nhận hàng cha và các hàng thuộc tính được xóa theo schema.
8. Để phiên hết hạn, xác nhận cleanup xử lý đúng hàng cha và hàng con.
9. Thử tạo dữ liệu trùng **SESSION_ID**, xác nhận unique constraint từ chối.
10. Kiểm tra migration schema trên bản sao dữ liệu đang có trước khi rollout.

Ngoài kiểm thử database, hãy kiểm thử HTTP end-to-end qua **SessionRepositoryFilter**. Điều đó xác nhận cookie hoặc header mang **SESSION_ID**, còn **PRIMARY_ID** được giữ hoàn toàn trong tầng lưu trữ.

## 15. Quy tắc thiết kế và vận hành

Khi làm việc với Spring Session JDBC, giữ một số nguyên tắc sau:

- Dùng **SESSION_ID** cho việc nhận diện phiên từ request và API repository.
- Giữ **PRIMARY_ID** làm khóa nội bộ ổn định cho hàng phiên.
- Dùng **SESSION_PRIMARY_ID** để liên kết thuộc tính với hàng cha.
- Không gửi **PRIMARY_ID** cho client và không dùng nó thay session ID.
- Không dùng user ID làm một trong hai định danh persistence này.
- Không tự sửa hoặc xóa các hàng bằng SQL trong luồng nghiệp vụ thông thường.
- Giữ unique constraint, primary key, foreign key và index đúng với schema repository.
- Bảo vệ session ID như credential và giới hạn quyền đọc dữ liệu phiên.
- Kiểm thử ID rotation, expiration, invalidate và migration schema.

Trong môi trường nhiều instance, mọi instance cần dùng cùng database hoặc cụm database phiên và cùng cách hiểu schema. Nếu một instance dùng schema khác, nó có thể không tìm được hàng theo **SESSION_ID**, không tải được thuộc tính theo **PRIMARY_ID** hoặc ghi thất bại vì ràng buộc không tương thích. Schema migration cần được triển khai theo trình tự an toàn trước khi các phiên bản ứng dụng cùng truy cập.

## Kết luận

Trong Spring Session JDBC, **SESSION_ID** là định danh phiên được client gửi qua cookie hoặc header để repository tìm lại phiên. **PRIMARY_ID** là khóa chính nội bộ ổn định của hàng **SPRING_SESSION**, đồng thời là khóa được bảng **SPRING_SESSION_ATTRIBUTES** tham chiếu qua **SESSION_PRIMARY_ID**. Việc tách hai định danh cho phép session ID được xoay vòng mà quan hệ giữa phiên và các thuộc tính vẫn giữ nguyên. Hãy dùng API Spring Session để tạo, tìm, đổi ID và xóa phiên; giữ nguyên các ràng buộc schema; không gửi **PRIMARY_ID** cho client; và kiểm thử cả luồng HTTP lẫn quan hệ JDBC khi triển khai nhiều instance.
