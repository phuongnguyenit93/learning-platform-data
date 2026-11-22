# UTL_HTTP, network ACL, wallet và gọi dịch vụ bên ngoài

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Tích hợp phân tán  
> **Mục tiêu:** Gọi HTTP/HTTPS từ PL/SQL một cách có kiểm soát; cấu hình network ACL cho host và port; sử dụng Oracle Wallet để xác thực TLS và client certificate; phân biệt quyền database, quyền wallet và quyền filesystem; xử lý request/response, timeout, lỗi và credential; thiết kế outbound integration an toàn, có thể giám sát và vận hành.

## 1. Bức tranh tổng thể

UTL_HTTP là package PL/SQL cho phép Oracle Database gửi HTTP request tới dịch vụ bên ngoài. Ứng dụng có thể dùng package này để gọi REST API, webhook, dịch vụ xác thực hoặc endpoint nội bộ.

Một request HTTPS thành công cần nhiều điều kiện độc lập:

1. PL/SQL session có thể thực thi UTL_HTTP.
2. Principal thực thi có quyền network ACL phù hợp cho hostname và port.
3. Database server có thể phân giải DNS và mở kết nối TCP tới đích hoặc proxy.
4. OS account chạy Oracle Database có thể đọc wallet nếu wallet được sử dụng.
5. Wallet chứa trust chain phù hợp và/hoặc client credential cần thiết.
6. TLS handshake thành công, hostname và certificate hợp lệ.
7. HTTP endpoint chấp nhận method, header, credential và payload.
8. PL/SQL xử lý response, timeout, status code và lỗi đúng cách.

Có thể hình dung luồng như sau:

~~~text
PL/SQL application
       |
       v
    UTL_HTTP
       |
       +---- Network ACL: host / port / principal
       |
       +---- Oracle Wallet: trust / client cert / credentials
       |
       v
Oracle Database server process
       |
       +---- OS permission to read wallet
       |
       +---- DNS / firewall / proxy / route
       |
       v
External HTTP(S) service
       |
       v
HTTP status + headers + response body
~~~

Network ACL kiểm soát database user được phép kết nối tới host nào. Wallet hỗ trợ TLS trust và một số cơ chế xác thực bằng certificate/password. Quyền filesystem quyết định Oracle server process có thể đọc wallet hay không. Ba lớp này không thay thế nhau.

## 2. UTL_HTTP làm gì?

UTL_HTTP cung cấp các API để tạo request, thiết lập header, gửi body, nhận response và đọc dữ liệu.

Các thao tác thường gặp:

| API | Mục đích |
|---|---|
| SET_WALLET | Chọn wallet sử dụng cho TLS hoặc credential |
| SET_TRANSFER_TIMEOUT | Đặt timeout cho hoạt động truyền dữ liệu |
| SET_DETAILED_EXCP_SUPPORT | Bật thông tin exception chi tiết |
| BEGIN_REQUEST | Tạo HTTP request |
| SET_HEADER | Thiết lập request header |
| WRITE_TEXT / WRITE_RAW | Gửi request body |
| GET_RESPONSE | Gửi request và nhận response |
| GET_HEADER_COUNT / GET_HEADER | Đọc response headers |
| READ_TEXT / READ_RAW | Đọc response body |
| END_RESPONSE | Đóng response và giải phóng tài nguyên |
| SET_PROXY | Cấu hình HTTP proxy khi cần |
| SET_RESPONSE_ERROR_CHECK | Điều khiển cách xử lý HTTP error status |

Có thể dùng hàm tiện ích UTL_HTTP.REQUEST cho các request đơn giản, nhưng BEGIN_REQUEST/GET_RESPONSE phù hợp hơn khi cần header, body, status code, timeout và xử lý lỗi chi tiết.

### 2.1. HTTP status khác Oracle exception

Một request có thể kết nối và nhận response thành công ở tầng HTTP nhưng dịch vụ trả:

- 400 Bad Request.
- 401 Unauthorized.
- 403 Forbidden.
- 404 Not Found.
- 429 Too Many Requests.
- 500 Internal Server Error.
- 503 Service Unavailable.

Đây là HTTP status code. Nó không nhất thiết tạo Oracle exception. Ứng dụng phải đọc STATUS_CODE và REASON_PHRASE để quyết định nghiệp vụ.

Ngược lại, ORA-24247 hoặc ORA-29024 là lỗi xảy ra trước hoặc trong quá trình thiết lập network/TLS, chưa chắc có HTTP response.

### 2.2. UTL_HTTP không phải application gateway

UTL_HTTP là API gọi HTTP từ database. Nó không tự cung cấp đầy đủ chức năng của API gateway hoặc integration platform:

- Không tự quản lý vòng đời OAuth token theo nghiệp vụ.
- Không tự đảm bảo retry an toàn.
- Không tự bảo đảm exactly-once.
- Không tự quản lý circuit breaker theo service.
- Không thay thế hàng đợi/message broker.
- Không tự xác minh tính đúng đắn của response payload.

Thiết kế cần bổ sung timeout, retry policy, idempotency, logging, credential management và giới hạn tài nguyên.

## 3. Network ACL: cho phép kết nối tới host

Oracle Network Access Control List (network ACL) quy định principal nào được phép truy cập network endpoint. Với UTL_HTTP, cần xem quyền truy cập host và port.

Từ Oracle Database 12c, cách quản lý phổ biến là thêm ACE (Access Control Entry) bằng DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE. Các API ACL XML cũ như CREATE_ACL, ADD_PRIVILEGE và ASSIGN_ACL thuộc mô hình cũ/deprecated trong các release mới; hãy dùng API phù hợp với release đang chạy.

### 3.1. Quyền connect

Ví dụ cho phép schema APP_SCHEMA kết nối tới api.example.com trên HTTPS port 443:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(
        host       => 'api.example.com',
        lower_port => 443,
        upper_port => 443,
        ace        => xs$ace_type(
            privilege_list => xs$name_list('connect'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

Ý nghĩa:

- HOST là hostname đích.
- LOWER_PORT và UPPER_PORT giới hạn port được phép.
- PRIVILEGE_LIST chứa quyền network.
- PRINCIPAL_NAME là database user được cấp quyền.
- PRINCIPAL_TYPE xác định loại principal.

Giới hạn đúng hostname và port giúp giảm phạm vi outbound access. Nếu chỉ cần HTTPS, không cấp dải port rộng từ 1 đến 65535.

### 3.2. Quyền resolve cho DNS

Khi dùng hostname, database cần phân giải tên. Có thể cấp resolve riêng:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(
        host => 'api.example.com',
        ace  => xs$ace_type(
            privilege_list => xs$name_list('resolve'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

Quyền resolve không gắn với port range. Nó cho phép principal phân giải hostname theo quy tắc ACL.

Trong nhiều cấu hình, quyền connect là quyền chính để mở network connection; resolve cần thiết khi luồng sử dụng DNS hostname. Cấp đúng quyền theo release và cách endpoint được phân giải. Không cấp quyền resolve cho mọi host nếu chỉ cần một hostname cụ thể.

### 3.3. Cấp theo host cụ thể

Ưu tiên:

~~~text
api.example.com
payments.internal.example
identity.example.net
~~~

Tránh cấp wildcard rộng nếu không có yêu cầu:

~~~text
*
*.example.com
~~~

Wildcard có thể mở quyền truy cập tới nhiều hệ thống hơn dự định. Nếu ứng dụng bị lỗi hoặc bị khai thác, phạm vi host được phép càng rộng thì rủi ro outbound càng lớn.

### 3.4. ACL không phải firewall

Network ACL là kiểm soát ở tầng Oracle Database. Nó không:

- Mở firewall hoặc security group.
- Tạo route tới network.
- Cấp quyền DNS resolver ở OS.
- Cấu hình proxy.
- Cho phép OS account đọc wallet.
- Bảo đảm endpoint đang hoạt động.

Database host vẫn cần firewall egress, DNS, routing và proxy policy phù hợp. Nên có cả allowlist ở Oracle ACL và network firewall.

## 4. Kiểm tra network ACL

### 4.1. Xem host ACE

DBA có thể xem ACE hiện tại:

~~~sql
SELECT host,
       lower_port,
       upper_port,
       ace_order,
       grant_type,
       principal,
       privilege,
       start_date,
       end_date
FROM dba_host_aces
ORDER BY host, lower_port, principal, privilege;
~~~

Dùng view tương ứng với quyền hiện có, chẳng hạn USER_HOST_ACES hoặc ALL_HOST_ACES nếu được hỗ trợ và cấp quyền.

Kiểm tra:

- Host có đúng FQDN không?
- Port có bị cấp rộng không?
- Principal có phải schema thực thi không?
- Privilege có đúng connect/resolve không?
- Grant có thời hạn không?
- Có ACE deny hoặc thứ tự ACE ảnh hưởng kết quả không?

### 4.2. Xem wallet ACE

~~~sql
SELECT wallet_path,
       ace_order,
       grant_type,
       principal,
       privilege,
       start_date,
       end_date
FROM dba_wallet_aces
ORDER BY wallet_path, principal, privilege;
~~~

Nếu ứng dụng dùng client certificate hoặc password trong wallet, kiểm tra đúng wallet path và principal.

### 4.3. Thu hồi ACE

Khi endpoint không còn cần truy cập, DBA có thể dùng DBMS_NETWORK_ACL_ADMIN.REMOVE_HOST_ACE hoặc REMOVE_WALLET_ACE với thông tin ACE tương ứng. Xác nhận cú pháp theo release và kiểm tra lại dictionary view sau khi thu hồi.

Không xóa toàn bộ ACL của host nếu nhiều ứng dụng khác vẫn phụ thuộc. Thu hồi đúng ACE/principal/privilege.

### 4.4. Lỗi ORA-24247

ORA-24247: network access denied by access control list (ACL) thường cho biết principal thực thi chưa có quyền network cần thiết cho host/port.

Quy trình điều tra:

1. Xác định database user và PL/SQL call stack.
2. Xác định hostname/port thực tế mà request đang kết nối.
3. Xác định request có qua proxy hoặc redirect không.
4. Kiểm tra DBA_HOST_ACES.
5. Kiểm tra quyền được grant cho principal phù hợp.
6. Bổ sung ACE tối thiểu.
7. Thử lại bằng cùng account và cùng execution context.

Không giải quyết bằng cách grant quyền cho PUBLIC hoặc wildcard host.

## 5. Principal nào cần ACL khi gọi từ package?

Khi UTL_HTTP được gọi trực tiếp trong anonymous block, principal thường là user đang thực thi session.

Khi UTL_HTTP nằm trong stored PL/SQL unit, phải xét AUTHID:

- AUTHID DEFINER: code chạy theo quyền của owner trong ngữ cảnh definer-rights.
- AUTHID CURRENT_USER: code chạy theo quyền của invoker theo quy tắc invoker-rights.

Do đó, schema cần được cấp ACE phụ thuộc vào ngữ cảnh thực thi. Không mặc định rằng người đăng nhập ứng dụng luôn là principal được kiểm tra khi lời gọi nằm trong definer-rights package.

Ví dụ package:

~~~sql
CREATE OR REPLACE PACKAGE api_owner.external_api
AUTHID DEFINER
AS
    PROCEDURE check_service;
END external_api;
/
~~~

Nếu code trong package thực thi network call theo definer rights, cần đánh giá quyền network của API_OWNER. Nếu dùng invoker rights, kiểm tra quyền của invoker. Test bằng chính user ứng dụng và call path production.

Không cấp ACE cho mọi user chỉ để tránh lỗi trong một package. Ghi rõ AUTHID và principal trong thiết kế.

## 6. Oracle Wallet và HTTPS

HTTPS sử dụng TLS để bảo vệ dữ liệu truyền và xác minh danh tính server. Oracle Wallet có thể chứa:

- Trusted root CA certificates.
- Intermediate CA certificates.
- User/client certificate.
- Private key tương ứng.
- Credential/password theo tính năng được hỗ trợ.

Đối với HTTPS server authentication, wallet được UTL_HTTP sử dụng để xác minh certificate chain theo trust anchors đã cấu hình.

Đối với mutual TLS (mTLS), client cũng phải trình certificate và chứng minh quyền sở hữu private key khi server yêu cầu.

### 6.1. Trust chain

Ví dụ certificate chain:

~~~text
API server certificate
       |
       v
Intermediate CA
       |
       v
Root CA
~~~

Wallet cần trust anchor phù hợp và intermediate certificates cần thiết theo cách server cung cấp chain. Nếu thiếu CA hoặc certificate hết hạn, TLS handshake có thể thất bại.

Certificate server cũng phải khớp hostname mà ứng dụng gọi, thông thường thông qua Subject Alternative Name (SAN). Certificate còn hạn nhưng SAN không khớp vẫn có thể bị từ chối.

### 6.2. Tạo wallet

Ví dụ tạo wallet có auto-login trên database server:

~~~bash
orapki wallet create \
  -wallet /u01/app/oracle/wallets/api \
  -auto_login
~~~

Lệnh được chạy trên host phù hợp với Oracle Wallet tooling và theo quy trình bảo mật của tổ chức. Có thể cần nhập password wallet tùy lựa chọn.

Thêm trusted certificate:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/wallets/api \
  -trusted_cert \
  -cert root-ca.pem
~~~

Nếu chain cần intermediate CA, thêm certificate tương ứng theo thứ tự và quy trình PKI được phê duyệt.

Xem nội dung wallet:

~~~bash
orapki wallet display \
  -wallet /u01/app/oracle/wallets/api
~~~

Không lấy certificate tùy tiện từ một nguồn không xác minh. Certificate phải được xác nhận fingerprint/issuer và nguồn phát hành tin cậy.

### 6.3. Auto-login wallet

Wallet có thể có:

- ewallet.p12: wallet được bảo vệ bằng password.
- cwallet.sso: auto-login wallet được Oracle sử dụng để mở wallet theo cấu hình.

Auto-login giúp ứng dụng không phải đưa wallet password vào PL/SQL code, nhưng làm cho quyền đọc file trở nên quan trọng. Bất kỳ OS principal nào đọc được auto-login wallet có thể có khả năng sử dụng nội dung wallet theo quyền của file đó.

Bảo vệ thư mục và file wallet, hạn chế owner/group, backup wallet an toàn và có quy trình xoay vòng certificate/key.

### 6.4. OS permission trên wallet

Wallet path là path phía database server. OS account chạy Oracle Database phải có quyền đọc file wallet và traverse các thư mục cha.

Ví dụ kiểm tra trên Linux:

~~~bash
ls -ld /u01/app/oracle/wallets/api
ls -l /u01/app/oracle/wallets/api
namei -l /u01/app/oracle/wallets/api
~~~

Không dùng chmod 777. Quyền filesystem nên giới hạn ở account/group cần thiết. Trên Windows, kiểm tra NTFS ACL của Oracle Database service account.

### 6.5. Thiết lập wallet trong UTL_HTTP

Ví dụ:

~~~sql
BEGIN
    UTL_HTTP.SET_WALLET(
        path     => 'file:/u01/app/oracle/wallets/api',
        password => NULL
    );
END;
/
~~~

Với password-protected wallet, truyền password qua cơ chế secret management được tổ chức phê duyệt; không hardcode password trong package source hoặc script chia sẻ.

Đường dẫn phải trỏ tới wallet directory trên server, có prefix file: theo cú pháp UTL_HTTP. Nó không phải đường dẫn trên máy chạy SQL Developer hoặc máy chạy expdp.

### 6.6. Không tắt xác minh TLS

Không khắc phục ORA-29024 bằng cách vô hiệu hóa certificate validation hoặc chấp nhận certificate không tin cậy.

Kiểm tra:

- Wallet có đúng root/intermediate CA không?
- Server có gửi đủ chain không?
- Certificate có hết hạn hoặc chưa có hiệu lực không?
- SAN có khớp hostname không?
- Server và database có clock chính xác không?
- Wallet path có đúng và OS-readable không?
- Có proxy TLS inspection thay certificate không?

Nếu có TLS inspection proxy, CA của proxy phải được phê duyệt và trust theo chính sách bảo mật.

## 7. Wallet ACL cho client certificate và password

Ngoài host ACE, Oracle có wallet ACE để kiểm soát principal được dùng credential trong wallet.

### 7.1. Client certificate

Nếu ứng dụng dùng client certificate để xác thực mTLS, có thể cần cấp quyền use_client_certificates trên wallet:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_WALLET_ACE(
        wallet_path => 'file:/u01/app/oracle/wallets/api',
        ace         => xs$ace_type(
            privilege_list => xs$name_list('use_client_certificates'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

Wallet phải chứa client certificate và private key phù hợp. Remote server cũng phải tin CA phát hành client certificate và có policy xác thực certificate đó.

### 7.2. Password credentials trong wallet

Nếu ứng dụng sử dụng password credential được lưu trong wallet theo API Oracle hỗ trợ, có thể cần privilege use_passwords:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_WALLET_ACE(
        wallet_path => 'file:/u01/app/oracle/wallets/api',
        ace         => xs$ace_type(
            privilege_list => xs$name_list('use_passwords'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

Chỉ cấp privilege wallet cần thiết. Không cấp cả use_client_certificates và use_passwords nếu ứng dụng không sử dụng các cơ chế đó.

Wallet ACE không thay thế host ACE. Principal vẫn cần network permission để kết nối tới endpoint.

### 7.3. Wallet trust và client authentication khác nhau

- Trust certificate giúp client xác minh server.
- Client certificate giúp server xác minh client.
- Password credential hỗ trợ một số cơ chế xác thực.
- Network ACL quyết định principal có được kết nối tới host/port không.

Không nhầm việc cài root CA vào wallet với việc cấp quyền network ACL.

## 8. Gọi HTTPS GET bằng UTL_HTTP

Ví dụ dưới đây gửi GET tới endpoint health, đọc status và response body, rồi luôn đóng response khi hoàn tất.

~~~sql
DECLARE
    l_req           UTL_HTTP.REQ;
    l_resp          UTL_HTTP.RESP;
    l_buffer        VARCHAR2(32767);
    l_response_open BOOLEAN := FALSE;
BEGIN
    UTL_HTTP.SET_DETAILED_EXCP_SUPPORT(TRUE);
    UTL_HTTP.SET_TRANSFER_TIMEOUT(30);

    UTL_HTTP.SET_WALLET(
        path     => 'file:/u01/app/oracle/wallets/api',
        password => NULL
    );

    l_req := UTL_HTTP.BEGIN_REQUEST(
        url          => 'https://api.example.com/v1/health',
        method       => 'GET',
        http_version => 'HTTP/1.1'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'User-Agent',
        'Oracle-Database-Integration'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Accept',
        'application/json'
    );

    l_resp := UTL_HTTP.GET_RESPONSE(l_req);
    l_response_open := TRUE;

    DBMS_OUTPUT.PUT_LINE(
        'HTTP status: ' || l_resp.status_code ||
        ' ' || l_resp.reason_phrase
    );

    BEGIN
        LOOP
            UTL_HTTP.READ_TEXT(l_resp, l_buffer, 32767);
            DBMS_OUTPUT.PUT_LINE(SUBSTR(l_buffer, 1, 2000));
        END LOOP;
    EXCEPTION
        WHEN UTL_HTTP.END_OF_BODY THEN
            NULL;
    END;

    UTL_HTTP.END_RESPONSE(l_resp);
    l_response_open := FALSE;

EXCEPTION
    WHEN OTHERS THEN
        IF l_response_open THEN
            BEGIN
                UTL_HTTP.END_RESPONSE(l_resp);
            EXCEPTION
                WHEN OTHERS THEN
                    NULL;
            END;
        END IF;

        RAISE;
END;
/
~~~

Ví dụ minh họa cần thay hostname, wallet path và endpoint bằng giá trị đã được phê duyệt. Không ghi response payload nhạy cảm vào DBMS_OUTPUT hoặc application log.

### 8.1. Vì sao phải gọi END_RESPONSE?

Response giữ network resource và trạng thái đọc. Nếu không đóng response, session có thể giữ connection/resource lâu hơn cần thiết.

Trong code production:

- Đóng response khi đọc hết body.
- Đóng response khi có exception sau khi GET_RESPONSE thành công.
- Không nuốt exception gốc chỉ vì cleanup thất bại.
- Giới hạn kích thước body và thời gian xử lý.
- Không lưu toàn bộ response lớn vào VARCHAR2.

### 8.2. Đọc response headers

Có thể xem header count và từng header:

~~~sql
DECLARE
    l_resp   UTL_HTTP.RESP;
    l_name   VARCHAR2(256);
    l_value  VARCHAR2(4000);
    l_index  PLS_INTEGER;
BEGIN
    -- Sau khi GET_RESPONSE đã trả về l_resp:
    l_index := 1;

    WHILE l_index <= UTL_HTTP.GET_HEADER_COUNT(l_resp) LOOP
        UTL_HTTP.GET_HEADER(
            l_resp,
            l_index,
            l_name,
            l_value
        );

        DBMS_OUTPUT.PUT_LINE(l_name || ': ' || l_value);
        l_index := l_index + 1;
    END LOOP;
END;
/
~~~

Đây là phần xử lý đặt sau GET_RESPONSE trong cùng block; không gọi nó với response chưa được khởi tạo.

## 9. Xử lý HTTP status code

HTTP 2xx thường biểu thị thành công ở tầng giao thức, nhưng vẫn cần xác minh body theo contract.

Ví dụ:

~~~sql
IF l_resp.status_code BETWEEN 200 AND 299 THEN
    -- Xử lý response thành công theo API contract.
    NULL;
ELSIF l_resp.status_code = 401 THEN
    -- Credential/token không hợp lệ hoặc hết hạn.
    NULL;
ELSIF l_resp.status_code = 429 THEN
    -- Rate limit: áp dụng backoff theo Retry-After nếu có.
    NULL;
ELSIF l_resp.status_code >= 500 THEN
    -- Dịch vụ phía server có lỗi hoặc tạm thời không sẵn sàng.
    NULL;
ELSE
    -- 4xx hoặc status khác: xử lý theo hợp đồng API.
    NULL;
END IF;
~~~

Không coi mọi response nhận được là thành công. Một request HTTP 200 cũng có thể chứa business error trong JSON. Cần parse payload và xác minh mã nghiệp vụ.

UTL_HTTP.SET_RESPONSE_ERROR_CHECK có thể thay đổi cách package báo lỗi đối với HTTP client/server status. Nếu bật, các status thuộc nhóm lỗi có thể được chuyển thành exception tương ứng. Chọn một cách xử lý nhất quán: hoặc kiểm tra status thủ công, hoặc bật error check và xử lý exception phù hợp.

## 10. Gửi POST JSON

Ví dụ gửi JSON UTF-8. Body được chuyển thành RAW để tính Content-Length theo số byte thay vì số ký tự.

~~~sql
DECLARE
    l_req       UTL_HTTP.REQ;
    l_resp      UTL_HTTP.RESP;
    l_body      VARCHAR2(32767) := '{"orderId":1001,"status":"PAID"}';
    l_body_raw  RAW(32767);
    l_buffer    VARCHAR2(32767);
    l_open      BOOLEAN := FALSE;
BEGIN
    UTL_HTTP.SET_TRANSFER_TIMEOUT(30);
    UTL_HTTP.SET_WALLET(
        'file:/u01/app/oracle/wallets/api',
        NULL
    );

    l_body_raw := UTL_I18N.STRING_TO_RAW(l_body, 'AL32UTF8');

    l_req := UTL_HTTP.BEGIN_REQUEST(
        'https://api.example.com/v1/orders',
        'POST',
        'HTTP/1.1'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Content-Type',
        'application/json; charset=UTF-8'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Accept',
        'application/json'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Content-Length',
        TO_CHAR(UTL_RAW.LENGTH(l_body_raw))
    );

    UTL_HTTP.WRITE_RAW(l_req, l_body_raw);

    l_resp := UTL_HTTP.GET_RESPONSE(l_req);
    l_open := TRUE;

    DBMS_OUTPUT.PUT_LINE(
        'HTTP status: ' || l_resp.status_code
    );

    BEGIN
        LOOP
            UTL_HTTP.READ_TEXT(l_resp, l_buffer, 32767);
            DBMS_OUTPUT.PUT_LINE(SUBSTR(l_buffer, 1, 2000));
        END LOOP;
    EXCEPTION
        WHEN UTL_HTTP.END_OF_BODY THEN
            NULL;
    END;

    UTL_HTTP.END_RESPONSE(l_resp);
    l_open := FALSE;

EXCEPTION
    WHEN OTHERS THEN
        IF l_open THEN
            BEGIN
                UTL_HTTP.END_RESPONSE(l_resp);
            EXCEPTION
                WHEN OTHERS THEN
                    NULL;
            END;
        END IF;
        RAISE;
END;
/
~~~

Ví dụ dùng body nhỏ. Với payload lớn, xử lý CLOB/RAW theo từng chunk, tính byte length đúng theo encoding hoặc dùng cơ chế truyền mà endpoint hỗ trợ. Không giả định LENGTH(text) luôn bằng Content-Length của UTF-8.

### 10.1. Authorization header

Một API có thể yêu cầu bearer token:

~~~sql
UTL_HTTP.SET_HEADER(
    l_req,
    'Authorization',
    'Bearer ' || l_access_token
);
~~~

Token phải được lấy từ secret store hoặc cơ chế credential được tổ chức phê duyệt. Không hardcode token trong package source, không lưu vào bảng log, không in ra DBMS_OUTPUT.

Nếu token hết hạn, áp dụng quy trình refresh có kiểm soát. Tránh để nhiều session đồng thời refresh cùng một token gây request storm.

### 10.2. Basic authentication

Một số API dùng HTTP Basic authentication. Basic authentication chỉ mã hóa Base64 credential ở header, không mã hóa bí mật; chỉ sử dụng qua HTTPS với certificate validation hợp lệ.

Nếu dùng credential trong Oracle Wallet, xem API wallet credential được hỗ trợ và quyền use_passwords. Không lưu username/password trong source code hoặc URL query string.

## 11. Timeout, retry và quản lý tài nguyên

### 11.1. Transfer timeout

~~~sql
BEGIN
    UTL_HTTP.SET_TRANSFER_TIMEOUT(30);
END;
/
~~~

Đặt timeout phù hợp SLA và thời gian xử lý endpoint. Timeout quá dài có thể giữ session database và resource trong thời gian lâu. Timeout quá ngắn có thể tạo lỗi giả khi endpoint có độ trễ hợp lệ.

SET_TRANSFER_TIMEOUT tác động tới hoạt động truyền dữ liệu của UTL_HTTP trong session. Không giả định nó thay thế mọi timeout ở DNS, TCP, proxy, load balancer hoặc tầng ứng dụng.

### 11.2. Retry có giới hạn

Retry phù hợp với một số lỗi tạm thời:

- 429 Too Many Requests.
- 502/503/504.
- Một số lỗi kết nối hoặc timeout có thể phục hồi.

Nhưng không retry mọi lỗi:

- 400 thường là request không hợp lệ.
- 401/403 thường cần xử lý credential/authorization.
- 404 có thể là endpoint hoặc resource không tồn tại.
- 409 có thể là conflict nghiệp vụ.
- POST có thể đã được xử lý dù client timeout trước khi nhận response.

Retry nên có:

- Số lần tối đa.
- Exponential backoff và jitter.
- Tổng thời gian tối đa.
- Xử lý Retry-After nếu có.
- Idempotency key với thao tác tạo/cập nhật có side effect.
- Log attempt count và correlation ID.

### 11.3. Không giữ transaction lock trong lúc gọi network

Một transaction database không nên giữ row lock lâu trong khi chờ dịch vụ HTTP nếu có thể tránh.

Ví dụ nguy hiểm:

1. BEGIN transaction.
2. UPDATE order và giữ lock.
3. Gọi API bên ngoài mất 30 giây.
4. Chờ response rồi COMMIT.

Trong thời gian đó, session giữ lock và transaction resources. Nếu API chậm, database contention có thể tăng.

Một pattern thường tốt hơn:

1. Ghi thay đổi nghiệp vụ và outbox event trong cùng transaction.
2. COMMIT.
3. Worker/job đọc outbox.
4. Gọi dịch vụ ngoài transaction ngắn.
5. Ghi kết quả và retry theo trạng thái.
6. Dùng idempotency key để tránh side effect trùng.

Pattern outbox giúp phối hợp transaction database và HTTP service mà không giữ transaction mở trong thời gian network call.

## 12. Proxy và outbound network

Một số môi trường yêu cầu HTTP proxy để đi ra ngoài.

UTL_HTTP có API SET_PROXY để cấu hình proxy theo session. Ví dụ khái niệm:

~~~sql
BEGIN
    UTL_HTTP.SET_PROXY(
        proxy            => 'proxy.internal.example:8080',
        no_proxy_domains => 'internal.example'
    );
END;
/
~~~

Cú pháp, proxy authentication và TLS inspection cần kiểm tra theo Oracle release và môi trường.

Khi dùng proxy:

- Database host phải kết nối được tới proxy.
- Firewall phải cho phép kết nối tới proxy host/port.
- Network ACL phải phù hợp với endpoint và routing thực tế.
- Proxy có thể thực hiện TLS inspection và thay certificate.
- Wallet phải tin CA được phê duyệt nếu proxy kết thúc TLS.
- no_proxy_domains phải được cấu hình chính xác.
- Proxy logs và database logs cần correlation ID.

Không đưa password proxy vào code hoặc parameter file công khai.

## 13. ACL, wallet và UTL_HTTP: ma trận quyền

| Hoạt động | Kiểm soát chính |
|---|---|
| Kết nối tới api.example.com:443 | Host ACE connect |
| Phân giải api.example.com | Host ACE resolve khi cần |
| Xác minh TLS server certificate | Wallet trust chain và TLS configuration |
| Trình client certificate | Wallet chứa cert/key và use_client_certificates ACE khi cần |
| Lấy password credential từ wallet | use_passwords ACE khi API sử dụng |
| Đọc wallet file | OS permission của Oracle Database service account |
| Kết nối qua proxy | ACL/network route/firewall theo đường đi thực tế |
| Gửi HTTP request | UTL_HTTP execution privilege và API contract |
| Đọc/ghi dữ liệu ứng dụng | Quyền bảng/package riêng, không do network ACL cấp |

Network ACL không cấp SELECT/UPDATE trên bảng. Wallet ACE không cấp host connect. OS permission không thay thế database privilege.

## 14. Chẩn đoán lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| ORA-24247 | Thiếu network ACL privilege | Principal, hostname, port, host ACE |
| ORA-29273 | UTL_HTTP request failed, lỗi bao ngoài | Xem detailed SQL error và exception stack |
| ORA-29024 | Certificate validation failure | Trust chain, expiry, SAN, clock, proxy |
| ORA-28759 | Không mở được wallet/file | Wallet path, file tồn tại, OS permission |
| ORA-29257 | Host unknown | DNS, resolver, resolve ACE |
| ORA-29260 | Network error | Route, firewall, proxy, remote endpoint |
| ORA-29276 | Transfer timeout | Endpoint latency, network, timeout value |
| HTTP 401 | Credential/token không hợp lệ | Token expiry, auth scheme, wallet credential |
| HTTP 403 | Server từ chối quyền | API scope/role, mTLS identity, policy |
| HTTP 404 | Endpoint/resource sai | URL, API version, path |
| HTTP 429 | Rate limit | Backoff, request rate, Retry-After |
| HTTP 5xx | Dịch vụ ngoài lỗi | Remote health, retry policy, circuit breaker |
| Response rỗng | Endpoint trả body rỗng hoặc đọc sai | Status, Content-Length, transfer encoding |
| Unicode sai | Encoding mismatch | Content-Type charset, AL32UTF8 conversion |
| Chỉ một node RAC lỗi | Wallet/path/DNS/ACL không đồng nhất | Mount, file permission, node configuration |

### 14.1. Bật detailed exception support

~~~sql
BEGIN
    UTL_HTTP.SET_DETAILED_EXCP_SUPPORT(TRUE);
END;
/
~~~

Trong exception handler có thể xem:

~~~sql
DBMS_OUTPUT.PUT_LINE(SQLERRM);
DBMS_OUTPUT.PUT_LINE(UTL_HTTP.GET_DETAILED_SQLERRM);
~~~

Thông tin lỗi chi tiết có thể chứa URL, hostname hoặc dữ liệu nhạy cảm. Khi ghi log, lọc token, credential và payload.

### 14.2. Phân loại theo tầng

Điều tra theo thứ tự:

1. **PL/SQL:** package có compile, caller có EXECUTE không?
2. **ACL:** principal có connect/resolve đúng host/port không?
3. **DNS/network:** database server phân giải và kết nối được không?
4. **Wallet/filesystem:** wallet đúng path, readable, certificate chain hợp lệ?
5. **TLS:** handshake, hostname, protocol và cipher có phù hợp?
6. **HTTP:** status code, headers, endpoint và auth?
7. **Business payload:** JSON/XML schema, encoding và business result?

Đừng thay certificate, ACL và firewall cùng lúc nếu chưa biết lỗi nằm ở tầng nào. Mỗi thay đổi nên có bằng chứng và bước xác minh.

## 15. Bảo mật outbound integration

Database có thể chứa dữ liệu nhạy cảm và quyền truy cập dữ liệu lớn. Nếu database user có thể gọi bất kỳ URL nào, một lỗi trong PL/SQL hoặc ứng dụng có thể trở thành đường truy cập tới hệ thống nội bộ.

### 15.1. SSRF và URL allowlist

Server-Side Request Forgery (SSRF) xảy ra khi input không tin cậy điều khiển destination mà server truy cập.

Không làm:

~~~sql
l_url := p_user_supplied_url;
l_resp := UTL_HTTP.GET_RESPONSE(UTL_HTTP.BEGIN_REQUEST(l_url));
~~~

Nếu người gọi có thể truyền URL tùy ý, họ có thể thử truy cập:

- localhost hoặc loopback.
- Link-local address.
- Cloud instance metadata endpoint.
- Private admin endpoint.
- Database/service nội bộ.
- Endpoint chỉ dành cho hạ tầng quản trị.

Thiết kế an toàn:

- URL/hostname được allowlist ở server.
- Chỉ dùng scheme HTTPS khi nghiệp vụ yêu cầu.
- Giới hạn port.
- Không cho caller truyền hostname tùy ý.
- Validate redirect destination.
- Chặn private/link-local/metadata ranges ở firewall/egress proxy.
- Quản lý DNS và tránh wildcard ACL.
- Không dựa vào client-side validation.

### 15.2. Redirects

HTTP 3xx có thể dẫn request sang hostname khác. Nếu ứng dụng tự động theo redirect, destination thực tế có thể khác URL ban đầu.

Với endpoint nhạy cảm:

- Kiểm tra status 3xx và Location.
- Chỉ follow redirect tới host đã allowlist.
- Không chuyển Authorization header sang host khác nếu không được phép.
- Giới hạn số lần redirect.
- Xác nhận ACL và egress firewall cho destination mới.

Không coi một URL đã allowlist là mọi redirect từ URL đó đều an toàn.

### 15.3. Không đưa credential vào URL

Tránh:

~~~text
https://api.example.com/data?token=secret
~~~

URL có thể xuất hiện trong log, proxy, tracing và error message. Dùng Authorization header hoặc cơ chế credential được API hỗ trợ.

### 15.4. TLS và certificate

- Chỉ dùng HTTPS cho dữ liệu/credential nhạy cảm.
- Xác minh hostname và certificate chain.
- Không chấp nhận certificate hết hạn hoặc self-signed không được phê duyệt.
- Bảo vệ private key trong wallet.
- Có lịch rotate certificate.
- Theo dõi expiry trước khi hết hạn.
- Giữ database server clock đồng bộ.

### 15.5. Least privilege

- Grant host ACE cho hostname/port cần thiết.
- Grant wallet ACE chỉ cho schema cần sử dụng.
- Không grant cho PUBLIC.
- Không dùng wildcard host nếu không cần.
- Không cấp CREATE ANY DIRECTORY hoặc quyền hệ thống rộng chỉ để wallet hoạt động.
- Giữ quyền filesystem wallet ở mức tối thiểu.
- Tách integration schema khỏi application owner nếu cần.

## 16. Gọi dịch vụ ngoài trong kiến trúc ứng dụng

### 16.1. Khi nào gọi trực tiếp từ database?

Có thể phù hợp khi:

- Request nhỏ và có timeout ngắn.
- Tích hợp là một phần của stored workflow đã được kiểm soát.
- Không cần throughput lớn.
- Network failure có thể được xử lý rõ ràng.
- Có owner vận hành endpoint và credential.
- Không giữ transaction/lock lâu.

### 16.2. Khi nào nên dùng application tier hoặc message broker?

Cân nhắc đưa HTTP call ra application tier khi:

- API call có latency biến động hoặc lâu.
- Cần OAuth token refresh phức tạp.
- Cần circuit breaker, rate limit và retry queue.
- Nhiều service hoặc tenant có endpoint khác nhau.
- Cần xử lý payload lớn.
- Cần scale outbound request độc lập với database.
- Cần observability/tracing ở cấp distributed system.
- Database transaction không nên phụ thuộc external availability.

Database nên tập trung vào transaction và persistence. Application tier hoặc integration platform thường phù hợp hơn để quản lý giao tiếp HTTP phức tạp.

### 16.3. Outbox pattern

Một ví dụ:

~~~text
Business transaction
       |
       +---- UPDATE ORDERS
       |
       +---- INSERT OUTBOX_EVENT
       |
       +---- COMMIT
                  |
                  v
             Outbox worker
                  |
                  v
             UTL_HTTP / API
                  |
                  v
             Remote service
                  |
                  v
        Mark delivered / retry
~~~

Outbox event được commit cùng thay đổi nghiệp vụ. Worker gửi HTTP sau commit. Nếu endpoint lỗi, event còn trạng thái pending để retry.

Cần có unique event ID, idempotency key, retry schedule, dead-letter state và monitoring backlog. Outbox không tự tạo exactly-once; remote API cần hỗ trợ idempotency hoặc consumer phải deduplicate.

## 17. Logging và observability

Mỗi outbound call nên ghi các trường:

- Request/correlation ID.
- Integration name.
- Target service name đã allowlist.
- HTTP method.
- Start/end timestamp.
- Elapsed time.
- HTTP status code.
- Retry count.
- Error class/code.
- Payload size.
- Response size.
- Business result.

Không ghi:

- Password.
- Bearer token.
- Private key.
- Wallet password.
- Full sensitive request/response payload.
- Personal data không cần thiết.

Dùng module/action hoặc correlation ID để liên kết database call với ứng dụng. Tạo metric cho success rate, timeout rate, 4xx/5xx, p95 latency, retry count và queue backlog.

### 17.1. Đo latency

Tách thời gian:

- Database processing trước call.
- DNS/connect/TLS setup.
- Time to first byte.
- Body transfer.
- JSON/XML parsing.
- Database commit sau response.

UTL_HTTP không thay thế distributed tracing toàn diện. Nếu cần trace xuyên application, proxy và external service, thiết kế correlation ID chung.

### 17.2. Circuit breaker và rate limit

Nếu endpoint lỗi liên tục, tiếp tục gọi có thể làm database sessions bị chiếm dụng. Có thể triển khai circuit breaker ở application tier hoặc job scheduler:

- Closed: cho request đi.
- Open: tạm dừng call khi lỗi vượt ngưỡng.
- Half-open: thử một số request để kiểm tra phục hồi.

Rate limit ngăn database tạo burst lớn vượt quota remote service. Retry phải có backoff và jitter, tránh tất cả session retry cùng lúc.

## 18. Runbook: cấu hình UTL_HTTP tới HTTPS endpoint

### Bước 1 — Xác định endpoint và owner

Ghi:

- Hostname FQDN.
- Port.
- Scheme.
- API owner.
- Authentication method.
- TLS requirements.
- Proxy requirement.
- Rate limit.
- Timeout/SLA.
- Data classification.

### Bước 2 — Xác minh network từ database host

Kiểm tra DNS, route, firewall, proxy và outbound policy từ chính database host. Kiểm tra không chỉ từ laptop DBA.

### Bước 3 — Chuẩn bị wallet

- Thu thập certificate chain từ nguồn tin cậy.
- Xác minh issuer, fingerprint, SAN và validity.
- Import trust certificates vào wallet.
- Import client certificate/private key nếu dùng mTLS.
- Bảo vệ wallet file và backup/key.
- Xác nhận Oracle service account đọc được.

### Bước 4 — Cấu hình network ACL

Cấp connect cho host/port và resolve khi cần, cho đúng principal thực thi. Nếu package dùng AUTHID DEFINER, xem package owner; nếu CURRENT_USER, xem invoker.

### Bước 5 — Cấu hình wallet ACE nếu cần

Cấp use_client_certificates hoặc use_passwords theo credential feature đang dùng. Không cấp rộng hơn nhu cầu.

### Bước 6 — Test bằng session thật

Chạy GET tới health endpoint bằng user và call path thực tế. Ghi HTTP status, response time và exception details đã lọc secret.

### Bước 7 — Test lỗi

Thử các tình huống trong môi trường test:

- Host không có ACL.
- Port sai.
- Wallet path sai.
- Certificate hết hạn/không tin cậy.
- Endpoint trả 401/429/500.
- Timeout.
- Response body lớn.
- Redirect sang host không allowlist.

### Bước 8 — Production readiness

- Có monitoring và alert.
- Có timeout/retry policy.
- Có credential rotation.
- Có owner endpoint và escalation.
- Có log retention và redaction.
- Có rollback ACL/wallet config.
- Có kiểm thử failover/network outage.

## 19. Các câu lệnh kiểm tra thường dùng

### 19.1. Network ACL

~~~sql
SELECT host,
       lower_port,
       upper_port,
       principal,
       privilege,
       grant_type
FROM dba_host_aces
WHERE principal = 'APP_SCHEMA'
ORDER BY host, lower_port, privilege;
~~~

### 19.2. Wallet ACL

~~~sql
SELECT wallet_path,
       principal,
       privilege,
       grant_type
FROM dba_wallet_aces
WHERE principal = 'APP_SCHEMA'
ORDER BY wallet_path, privilege;
~~~

### 19.3. Kiểm tra database/container identity

~~~sql
SELECT sys_context('USERENV', 'DB_NAME') AS db_name,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_USER') AS current_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

### 19.4. Kiểm tra UTL_HTTP availability

DBA kiểm tra package và quyền EXECUTE theo chính sách:

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE object_name = 'UTL_HTTP'
ORDER BY owner, object_type;
~~~

Không grant EXECUTE rộng cho PUBLIC chỉ để làm query test chạy được. Cấp quyền package cho integration schema theo security baseline.

## 20. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ grant ACL, không cấp OS permission | Oracle không đọc wallet hoặc không kết nối được | Kiểm tra OS account và filesystem |
| Chỉ cài certificate, không có host ACE | ORA-24247 | Grant connect/resolve đúng host |
| Grant ACL wildcard | Database có thể gọi nhiều endpoint ngoài dự kiến | Allowlist FQDN và port |
| Dùng wallet trên laptop | Database server không đọc được | Đặt wallet trên server-side path |
| Nhầm wallet trust với client certificate | TLS/mTLS cấu hình sai | Phân biệt server trust và client identity |
| Tắt TLS validation để hết ORA-29024 | Mất xác minh danh tính server | Sửa trust chain/SAN/clock |
| Không đóng response | Giữ network resource | Luôn END_RESPONSE |
| Không timeout | Session có thể bị giữ lâu | Đặt timeout theo SLA |
| Coi HTTP 500 là SQL exception | Không xử lý status code đúng | Đọc response status |
| Retry POST vô điều kiện | Tạo giao dịch trùng | Idempotency key và retry policy |
| Gọi API trong transaction đang giữ lock | Tăng lock duration và contention | Outbox/asynchronous worker |
| URL lấy từ input người dùng | SSRF tới endpoint nội bộ | Server-side allowlist và egress controls |
| Không xử lý redirect | Authorization có thể đi tới host khác | Validate Location và host |
| Log token/payload | Lộ credential/dữ liệu | Redaction và secret management |
| Chỉ test từ máy client | Không phản ánh network của database host | Test từ server/database session |
| Không kiểm tra RAC node | Một node có wallet/path khác | Đồng bộ wallet và OS access |

## 21. Bài thực hành

Thực hiện trên môi trường lab và endpoint test do tổ chức kiểm soát.

### Bài 1 — Tạo host ACE

Tạo ACL cho schema test chỉ tới một hostname và port 443. Query DBA_HOST_ACES để xác nhận.

### Bài 2 — Thử thiếu quyền

Gọi UTL_HTTP khi chưa có connect ACE. Ghi nhận ORA-24247, sau đó cấp quyền tối thiểu và thử lại.

### Bài 3 — DNS resolve

Thử hostname hợp lệ và hostname không phân giải được. Phân biệt ACL resolve với lỗi DNS/network.

### Bài 4 — Wallet trust

Tạo wallet test, import root/intermediate CA của endpoint test và cấu hình SET_WALLET. Kiểm tra TLS handshake.

### Bài 5 — Certificate lỗi

Dùng endpoint test có certificate không tin cậy hoặc hostname mismatch. Xác nhận lỗi TLS và khôi phục trust chain đúng.

### Bài 6 — mTLS

Tạo client certificate test, cấu hình wallet và use_client_certificates ACE. Xác nhận server nhận đúng client identity.

### Bài 7 — GET và status

Gọi endpoint trả 200, 401, 404 và 500. Xử lý status code riêng với Oracle exception.

### Bài 8 — POST UTF-8

Gửi JSON có ký tự Unicode. Tính Content-Length theo byte và xác nhận server nhận đúng payload.

### Bài 9 — Timeout

Gọi endpoint test có độ trễ. Thay SET_TRANSFER_TIMEOUT và đo thời gian/exception.

### Bài 10 — Response cleanup

Mô phỏng exception giữa lúc đọc body. Xác nhận END_RESPONSE được gọi.

### Bài 11 — SSRF control

Thử URL ngoài allowlist và redirect sang hostname khác. Xác nhận server-side validation và network egress policy chặn.

### Bài 12 — Outbox

Tạo outbox event, chạy worker gửi API, mô phỏng remote outage và retry. Xác nhận idempotency không tạo side effect trùng.

## 22. Checklist trước production

- [ ] Xác định endpoint FQDN, port, protocol và owner.
- [ ] Có allowlist server-side, không nhận URL tùy ý.
- [ ] Network ACL chỉ cấp host/port cần thiết.
- [ ] Grant connect và resolve phù hợp theo DNS usage.
- [ ] Principal ACL khớp AUTHID/call context thực tế.
- [ ] Firewall, DNS, route và proxy cho phép outbound có kiểm soát.
- [ ] Wallet nằm trên server path được bảo vệ.
- [ ] OS Oracle service account có quyền đọc wallet.
- [ ] Trust chain và hostname SAN được xác minh.
- [ ] Client certificate/private key được bảo vệ nếu dùng mTLS.
- [ ] Wallet ACE use_client_certificates/use_passwords chỉ cấp khi cần.
- [ ] Không hardcode token/password/private key.
- [ ] Timeout được đặt theo SLA.
- [ ] HTTP status và response body được xử lý rõ ràng.
- [ ] Response luôn được đóng khi thành công hoặc exception.
- [ ] Retry có giới hạn, backoff và idempotency.
- [ ] Không giữ transaction/row lock trong lúc chờ external service.
- [ ] Redirect được kiểm soát và không chuyển credential sang host khác.
- [ ] Log có correlation ID và redaction.
- [ ] Có metric success/error/timeout/latency/rate limit.
- [ ] Có runbook certificate rotation, ACL revoke và endpoint outage.
- [ ] Đã test bằng đúng database user/package owner và server environment.

## 23. Ghi nhớ cốt lõi

- UTL_HTTP cho phép PL/SQL gửi HTTP/HTTPS request từ Oracle Database tới dịch vụ bên ngoài.
- Network ACL kiểm soát principal được kết nối tới hostname/port; firewall và network route vẫn phải cho phép.
- Với API host cụ thể, grant connect trên port cần thiết và resolve khi DNS name resolution cần quyền đó.
- ACL không cấp quyền đọc wallet, không cấp quyền bảng và không tạo network route.
- DIRECTORY object và wallet path là hai khái niệm khác nhau; wallet path được UTL_HTTP tham chiếu trực tiếp theo cú pháp file URI.
- Wallet chứa trust certificate, client certificate/private key hoặc credential tùy mục tiêu; server trust và client authentication là hai việc khác nhau.
- OS account chạy Oracle Database phải đọc được wallet file; không dùng permission 777.
- Wallet ACE use_client_certificates/use_passwords chỉ cấp khi tính năng credential tương ứng cần dùng.
- AUTHID DEFINER và CURRENT_USER ảnh hưởng principal thực thi; grant ACL cho đúng context và test bằng user thật.
- ORA-24247 thường liên quan network ACL; ORA-29024 liên quan certificate validation; ORA-29273 là lỗi UTL_HTTP tổng quát cần xem detailed error.
- HTTP 4xx/5xx là response status và phải được xử lý riêng với Oracle exception.
- Luôn đặt timeout, giới hạn response, đóng response và ghi log đã lọc secret.
- Retry phải có giới hạn, backoff và idempotency; timeout sau POST không chứng minh server chưa xử lý request.
- Không giữ transaction hoặc row lock trong lúc chờ external service; cân nhắc outbox/asynchronous worker.
- Không nhận URL tùy ý từ user; chống SSRF bằng allowlist, ACL cụ thể, redirect validation và egress firewall.
- Không tắt TLS certificate validation để xử lý lỗi; sửa trust chain, SAN, expiry và clock.
- Gọi HTTP từ database phù hợp với tích hợp nhỏ, có kiểm soát; workload phức tạp thường nên được quản lý ở application/integration tier.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Packages and Types Reference — UTL_HTTP](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_HTTP.html) — HTTP request/response APIs, wallet, proxy, timeout and exception handling.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_NETWORK_ACL_ADMIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_NETWORK_ACL_ADMIN.html) — Host ACE, wallet ACE and network ACL administration.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Network access control, wallet privileges and least privilege.
- [Oracle Database Security Guide — Using Oracle Wallet](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Wallet management, certificates and credential protection.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Database server processes, operating-system access and administration.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_I18N](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_I18N.html) — Character set conversion for HTTP payloads.

Network ACL APIs, wallet behavior, TLS protocol support and UTL_HTTP features vary by Oracle release and platform. Confirm the exact database version, certificate requirements, package privileges and license terms; test ACL, wallet, timeout, redirect, response cleanup and failover in a representative non-production environment before production use.

