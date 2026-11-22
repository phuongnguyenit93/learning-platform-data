# Tạo broker instance ActiveMQ Artemis và xác định broker.xml, bootstrap.xml, management.xml

> **Chương:** Môi trường thực hành  
> **Công nghệ:** Apache ActiveMQ Artemis (thuộc module `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ`)  
> **Phạm vi:** Tạo một broker độc lập để thực hành queue/topic, routing và Java/JMS; biết chính xác nơi cấu hình broker, cơ chế khởi động và quyền quản trị.

## 1. Mục tiêu của bài thực hành

Sau bài này, bạn có thể:

1. Phân biệt thư mục cài đặt Artemis (`ARTEMIS_HOME`) với **broker instance** (`ARTEMIS_INSTANCE`), đồng thời tạo và chạy một instance trên Linux/macOS hoặc Windows.
2. Xác định đúng ba tệp `etc/broker.xml`, `etc/bootstrap.xml` và `etc/management.xml` trong instance mới.
3. Giải thích **tệp nào điều khiển acceptor, address, queue, routing, persistence; tệp nào khởi tạo broker và web console; tệp nào phân quyền thao tác quản trị/JMX**.
4. Cấu hình một queue thử nghiệm và kết nối từ Java bằng JMS, có xác thực, gửi message bền vững và nhận message trong JMS transaction.
5. Chẩn đoán các sự cố cổng mạng, cú pháp XML, xác thực, giao thức và quyền truy cập ở mức phòng lab.

**Điểm cần nhớ:** Trong Artemis, bản phân phối phần mềm và broker đang chạy là hai thứ khác nhau. Lệnh `artemis create` sinh ra **một instance với cấu hình, dữ liệu và script chạy riêng**. Khi sửa cấu hình thực hành, hãy sửa trong `ARTEMIS_INSTANCE/etc`, không sửa bản phân phối Artemis.

## 2. ARTEMIS_HOME và ARTEMIS_INSTANCE

ActiveMQ Artemis cung cấp broker cho giao tiếp bất đồng bộ. Ứng dụng có thể gửi command đến queue để một worker xử lý, hoặc phát event qua topic để nhiều subscription nhận. Artemis định tuyến message vào **address** và các **queue** theo routing type **anycast** hoặc **multicast**; các API JMS che bớt một phần mô hình nội bộ này.

Hai vị trí thường bị nhầm lẫn:

| Khái niệm | Chứa gì? | Vai trò |
|---|---|---|
| **`ARTEMIS_HOME`** | Bản Artemis đã tải/giải nén, thư viện, công cụ `bin/artemis` hoặc `bin/artemis.cmd` | Dùng để tạo instance; có thể giữ nguyên khi tạo nhiều instance. |
| **`ARTEMIS_INSTANCE`** | Script chạy instance, `etc/`, dữ liệu, log, tệp runtime | Nơi broker thực sự dùng cấu hình và lưu dữ liệu. |
| **Broker process** | JVM chạy Artemis với đường dẫn trỏ tới instance | Mở các cổng client, quản trị và xử lý message. |

Ví dụ cấu trúc sau khi tạo instance, với tên thư mục chỉ mang tính minh họa:

~~~text
/opt/apache-artemis-<version>/                  <-- ARTEMIS_HOME
└── bin/
    └── artemis                                <-- Công cụ tạo broker

/srv/artemis/lab01/                            <-- ARTEMIS_INSTANCE
├── bin/
│   └── artemis                                <-- Script chạy broker này
├── etc/
│   ├── broker.xml                             <-- Broker Core / routing / lưu trữ
│   ├── bootstrap.xml                          <-- Bootstrap / web console
│   ├── management.xml                         <-- JMX management / authorization
│   ├── login.config                           <-- JAAS login domain
│   ├── artemis-users.properties               <-- Người dùng (tùy cách cấu hình)
│   └── artemis-roles.properties               <-- Nhóm quyền (tùy cách cấu hình)
├── data/                                      <-- Journal/paging/bindings khi sử dụng
├── log/                                       <-- Log của instance
└── tmp/                                       <-- Tệp tạm, tùy bản phát hành
~~~

Cấu trúc thực tế có thể thêm các tệp `artemis.profile`, `artemis-utility.profile`, `logging.properties`, `jolokia-access.xml` hoặc thư mục khác theo phiên bản và lựa chọn tạo instance. Hãy lấy **tệp đã sinh trong instance thực tế** làm nguồn cấu hình, không giả định mọi bản Artemis có cấu trúc hoàn toàn giống nhau.

### Ba tệp cấu hình cần nhận diện

| Tệp trong `ARTEMIS_INSTANCE/etc` | Trách nhiệm chính | Khi nào cần xem hoặc sửa? |
|---|---|---|
| **`broker.xml`** | Cấu hình broker Core: tên broker, lưu trữ, acceptor/connector, address, queue, routing, `address-settings`, `security-settings`, các cơ chế vận hành khác | Muốn thay cổng client `61616`, khai báo queue/topic, DLQ, retry, quota hoặc quyền send/consume |
| **`bootstrap.xml`** | Cấu hình khởi động: tham chiếu `broker.xml`, JAAS domain, web server/console và ứng dụng web | Muốn kiểm tra broker nạp tệp nào hoặc console được bind trên cổng/địa chỉ nào (thường `8161`) |
| **`management.xml`** | Cấu hình management context và quyền truy cập quản trị, đặc biệt là thao tác JMX | Muốn giới hạn nhóm được xem hoặc thay đổi thuộc tính/quản lý broker qua giao diện quản trị tương ứng |

`broker.xml` và `management.xml` đều có thể chứa cấu hình bảo mật nhưng **không thay thế nhau**: `security-settings` trong `broker.xml` kiểm soát hành động messaging như gửi/nhận trên address; `role-access` trong `management.xml` kiểm soát các thao tác quản trị thuộc management context.

~~~mermaid
flowchart TD
    H[ARTEMIS_HOME/bin/artemis] -->|create| I[ARTEMIS_INSTANCE]
    I --> B[bin/artemis run]
    B --> S[etc/bootstrap.xml]
    S --> X[etc/broker.xml]
    S --> W[Web console: port 8161 thường dùng]
    I --> M[etc/management.xml]
    X --> A[Client acceptor: port 61616 thường dùng]
    X --> Q[Addresses / Queues / Routing]
    X --> D[(Journal / Paging / Persistence)]
    M --> J[JMX authorization]
~~~

Các cổng trên là **giá trị thường gặp của instance mặc định**, không phải cam kết cho mọi bản dựng hoặc môi trường. Cấu hình đang chạy mới quyết định địa chỉ/cổng cuối cùng.

## 3. Chuẩn bị môi trường

Bài lab dùng:

- Một JDK tương thích với **phiên bản Artemis đã chọn**; kiểm tra yêu cầu Java của bản phát hành đang dùng. Ví dụ thực hành dùng Java 17 cho mã mẫu.
- Bản phân phối **Apache ActiveMQ Artemis** đã giải nén; trong thư mục `bin` có lệnh `artemis` (Linux/macOS) hoặc `artemis.cmd` (Windows).
- Quyền tạo thư mục instance và mở cổng trên máy local.
- Hai cổng local dự kiến: `127.0.0.1:61616` cho JMS/Core; `127.0.0.1:8161` cho web console. Nếu cổng đã bị chiếm, đổi cấu hình trước khi khởi động.
- Maven hoặc IDE Java nếu thực hiện phần kiểm chứng JMS.

Có thể kiểm tra JDK bằng:

~~~bash
java -version
~~~

Không nên đặt broker instance **bên trong thư mục giải nén Artemis**. Nhiều instance có thể dùng chung bản phân phối nhưng cần **cổng mạng và thư mục dữ liệu riêng**. Nếu cùng cài hai instance `lab01` và `lab02`, chỉ đổi tên thư mục là chưa đủ; hai broker không thể cùng bind `127.0.0.1:61616` và `127.0.0.1:8161` trên một máy.

## 4. Tạo broker instance từ Artemis CLI

### 4.1. Linux hoặc macOS

Giả sử đã giải nén Artemis vào `/opt/apache-artemis-<version>`, và muốn tạo instance tại `/srv/artemis/lab01`. Đường dẫn có thể đổi theo quyền truy cập của người dùng.

~~~bash
# Điền thư mục phân phối Artemis thực tế:
ARTEMIS_HOME="/opt/apache-artemis-<version>"

# Chọn một thư mục instance chưa tồn tại:
ARTEMIS_INSTANCE="/srv/artemis/lab01"

# Tạo instance:
"$ARTEMIS_HOME/bin/artemis" create "$ARTEMIS_INSTANCE"
~~~

Lệnh `create` có thể hỏi tương tác về **username, password, role và quyền anonymous**. Các câu hỏi và tùy chọn CLI cụ thể phụ thuộc phiên bản. Với lab có xác thực, tạo user riêng (ví dụ `labuser`), role mà bạn kiểm soát (ví dụ `lab-admin`), đặt mật khẩu đủ mạnh, và không bật anonymous chỉ để bỏ qua lỗi đăng nhập.

Để chạy broker ở foreground:

~~~bash
"$ARTEMIS_INSTANCE/bin/artemis" run
~~~

Giữ cửa sổ terminal này mở để xem log khởi động và lỗi XML. Nhấn `Ctrl+C` khi cần dừng broker. Tùy nền tảng, có thể cài broker dưới dạng service; trong bài này dùng `run` để dễ thấy diễn biến.

### 4.2. Windows PowerShell

~~~powershell
# Điều chỉnh thành đường dẫn đã giải nén Artemis thực tế.
$artemisHome = "C:\tools\apache-artemis-<version>"
$instance = "C:\artemis-instances\lab01"

# Tạo instance trong một thư mục mới.
& "$artemisHome\bin\artemis.cmd" create $instance

# Chạy instance ở foreground.
& "$instance\bin\artemis.cmd" run
~~~

PowerShell cần toán tử gọi lệnh `&` nếu đường dẫn chương trình nằm trong chuỗi. Không chạy script `create` lần thứ hai lên một instance có dữ liệu cần giữ, và không sao chép tùy tiện thư mục `data/` giữa hai broker đang hoạt động.

### 4.3. Nhận biết lần tạo thành công

Sau khi `create` kết thúc:

1. Thư mục `ARTEMIS_INSTANCE` tồn tại.
2. Có script chạy broker trong `bin/`.
3. Có ít nhất ba tệp `etc/broker.xml`, `etc/bootstrap.xml`, `etc/management.xml` của instance.
4. Khi chạy `bin/artemis run`, log không báo lỗi cú pháp cấu hình, lỗi chiếm cổng hoặc lỗi quyền ghi thư mục dữ liệu.

Kiểm tra sự tồn tại tệp trên Linux/macOS:

~~~bash
test -f "$ARTEMIS_INSTANCE/etc/broker.xml" && echo "broker.xml: OK"
test -f "$ARTEMIS_INSTANCE/etc/bootstrap.xml" && echo "bootstrap.xml: OK"
test -f "$ARTEMIS_INSTANCE/etc/management.xml" && echo "management.xml: OK"
~~~

Trên Windows PowerShell, trong terminal có biến `$instance`:

~~~powershell
Test-Path -LiteralPath "$instance\etc\broker.xml"
Test-Path -LiteralPath "$instance\etc\bootstrap.xml"
Test-Path -LiteralPath "$instance\etc\management.xml"
~~~

Ba kết quả `True` xác nhận file tồn tại; **chưa** khẳng định nội dung XML hợp lệ hoặc broker thực sự đã đọc các tệp đó.

## 5. Đọc và cấu hình broker.xml

Mở `ARTEMIS_INSTANCE/etc/broker.xml`. Đây là nơi giải quyết ba câu hỏi căn bản:

- **Broker nghe ở đâu?** Kiểm tra mục `<acceptors>`.
- **Message đi về đâu?** Kiểm tra `<addresses>`, mỗi `<address>` và routing type bên trong.
- **Broker xử lý lỗi/quá tải và giới hạn quyền ra sao?** Kiểm tra `<address-settings>` và `<security-settings>`.

Artemis hỗ trợ nhiều giao thức; không phải cứ cổng mở là client dùng giao thức nào cũng kết nối được. Nếu Java dùng **Artemis JMS client dựa trên Core protocol**, acceptor phải cho phép `CORE`.

### 5.1. Acceptor phục vụ JMS local

Đoạn dưới minh họa **mục `<acceptors>` bên trong `<core>` có sẵn** trong `broker.xml`:

~~~xml
<acceptors>
    <acceptor name="lab-core">
        tcp://127.0.0.1:61616?protocols=CORE,AMQP
    </acceptor>
</acceptors>
~~~

Giải thích:

- `127.0.0.1` chỉ nhận kết nối từ chính máy chạy broker; phù hợp với lab local.
- `61616` là cổng message client thường dùng.
- `CORE` dành cho Artemis Core client, bao gồm Artemis JMS client trong ví dụ Java phía dưới.
- `AMQP` cho các client AMQP 1.0; việc có AMQP trong danh sách **không** đồng nghĩa mỗi client AMQP tự động hoạt động như JMS Core.

**Không dán thêm một `<acceptors>` thứ hai** nếu `broker.xml` đã có mục này. Hãy sửa acceptor hiện hữu hoặc thêm `<acceptor>` đúng vị trí, kiểm tra các cổng khác và tên cấu hình không xung đột. Không cần bật mọi giao thức trong môi trường local.

### 5.2. Address, anycast queue và multicast topic

Trong Artemis, `anycast` chuyển message đến một queue phù hợp, thường dùng để chia việc; `multicast` chuyển message tới nhiều queue/subscription liên quan, thường dùng cho topic/event.

Đoạn sau là nội dung **bên trong `<addresses>` đang tồn tại**, không phải một `broker.xml` hoàn chỉnh:

~~~xml
<address name="lab.orders">
    <anycast>
        <queue name="lab.orders"/>
    </anycast>
</address>

<address name="lab.events">
    <multicast/>
</address>
~~~

Ý nghĩa:

| Địa chỉ | Routing type | Hành vi mong đợi |
|---|---|---|
| `lab.orders` | `anycast` | Một queue chứa các job để nhiều consumer cạnh tranh nhận. |
| `lab.events` | `multicast` | Một event được phân phối đến các subscription/queue phù hợp theo cấu hình. |

Topic có thể phát event cho nhiều bên, nhưng điều kiện nhận lúc subscriber offline phụ thuộc loại subscription (durable hay non-durable). Chỉ tạo `<multicast/>` chưa tạo ra mọi durable subscription mà ứng dụng về sau sẽ dùng.

Một số instance bật `auto-create-addresses` hoặc `auto-create-queues`. Vì bài lab cần quan sát cấu hình rõ ràng, chúng ta **khai báo `lab.orders` tường minh** rồi kiểm chứng. Nếu broker đã có khai báo cùng tên, sửa đúng chỗ thay vì thêm trùng.

### 5.3. Redelivery, DLQ và giới hạn dung lượng

Ví dụ chính sách cho các địa chỉ bắt đầu bằng `lab.`, được đặt **bên trong `<address-settings>` hiện hữu**:

~~~xml
<address-setting match="lab.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
    <max-size-bytes>10485760</max-size-bytes>
    <address-full-policy>PAGE</address-full-policy>
</address-setting>
~~~

Các thông số minh họa:

- `lab.#` khớp nhóm address lab theo cú pháp wildcard Artemis.
- `redelivery-delay` là 1.000 ms trước lần giao lại tương ứng với cấu hình.
- `max-delivery-attempts` giới hạn số lần giao trước khi áp dụng xử lý dead-letter, tùy cơ chế quản lý message.
- `dead-letter-address` yêu cầu một address `DLQ` hợp lệ; nhiều template Artemis tạo sẵn `DLQ` và `ExpiryQueue`, **hãy xác nhận trước khi sử dụng**, không thêm trùng.
- `max-size-bytes` là một phần của cơ chế kiểm soát kích thước address; `PAGE` cho phép broker chuyển sang paging theo điều kiện cấu hình, **không** có nghĩa đĩa có dung lượng vô hạn.

Vì `address-settings` có quy tắc match và mặc định, cần kiểm tra xem `lab.#` có bị cấu hình cụ thể hơn ghi đè hay không. Chỉ thêm khi muốn thực hành retry/DLQ; không cần thay toàn bộ chính sách mặc định của broker.

### 5.4. Quyền gửi và nhận message

Nếu đã tạo role `lab-admin` ở bước `artemis create` và role đó thuộc user `labuser`, có thể giới hạn quyền trên address lab bằng đoạn **bên trong `<security-settings>` hiện hữu**:

~~~xml
<security-setting match="lab.#">
    <permission type="send" roles="lab-admin"/>
    <permission type="consume" roles="lab-admin"/>
</security-setting>
~~~

Ví dụ này minh họa riêng quyền gửi và nhận đối với address đã khai báo tường minh. Những nghiệp vụ tạo/xóa queue, tạo subscription, quản lý broker có quyền riêng; nếu đổi sang role `lab-producer`/`lab-consumer` thì phải khai báo role và gán user tương ứng. Đừng xóa các quy tắc mặc định khác nếu chưa hiểu tác động tới web console, DLQ hay các address hệ thống.

**Lưu ý:** Ví dụ XML ở các tiểu mục trên là **mảnh cấu hình**, dùng để thay hoặc bổ sung nội dung vào đúng section của file hiện hữu. Không ghép nguyên các đoạn thành một file mới thiếu phần root, namespace, schema và các cấu hình quan trọng mà `artemis create` đã tạo ra.

## 6. Đọc và cấu hình bootstrap.xml

Mở `ARTEMIS_INSTANCE/etc/bootstrap.xml`. Tệp này trả lời: **khi khởi động, Artemis nạp cấu hình broker nào và web console lắng nghe ở đâu?**

Một instance thông thường có các dòng/section mang ý nghĩa sau (đoạn minh họa, **giữ nguyên các khai báo ứng dụng web đã được sinh**):

~~~xml
<jaas-security domain="activemq"/>

<server configuration="file:${artemis.instance}/etc/broker.xml"/>

<web bind="http://127.0.0.1:8161" path="web">
    <!-- Giữ nguyên các phần tử <app .../> của bản phát hành hiện tại. -->
</web>
~~~

Đoạn trên **không phải toàn bộ nội dung bootstrap.xml**. File thực tế có thẻ root, namespace và các phần tử phụ thuộc phiên bản. Một vài điều cần phân biệt:

- `<server configuration="...">` trỏ tới **file broker Core** được nạp. Biểu thức `${artemis.instance}` được Artemis thay bằng đường dẫn instance tại runtime; không đổi thành đường dẫn của bản phân phối.
- `<jaas-security domain="activemq"/>` liên quan miền xác thực JAAS. File `login.config` và kho người dùng/role tùy cấu hình sẽ tham gia quá trình đăng nhập; thay domain phải đồng bộ với cấu hình JAAS tương ứng.
- `<web bind="...">` quyết định địa chỉ/cổng HTTP của web server tích hợp. `path="web"` không có nghĩa URL người dùng luôn kết thúc bằng `/web`: đường dẫn console còn phụ thuộc phần tử `<app>`.
- Địa chỉ thường truy cập console ở cấu hình tiêu chuẩn là `http://127.0.0.1:8161/console`, có thể chuyển hướng tùy bản phát hành. Không mở `0.0.0.0:8161` ra mạng ngoài khi chưa cấu hình TLS, xác thực và kiểm soát truy cập.

**Ví dụ phân biệt hai cổng:** muốn thay `tcp://127.0.0.1:61616` cho JMS, sửa acceptor trong `broker.xml`; muốn thay `http://127.0.0.1:8161` cho console, sửa `web bind` trong `bootstrap.xml`. Hai cổng phục vụ **hai loại kết nối khác nhau**.

## 7. Đọc và cấu hình management.xml

Mở `ARTEMIS_INSTANCE/etc/management.xml`. Artemis có các khả năng quản trị và giám sát qua JMX và giao diện quản trị tích hợp. Tệp này tập trung vào **quyền gọi phương thức quản trị**, không dùng để định nghĩa queue ứng dụng.

Ví dụ phần quyền (đặt **trong cấu trúc `<authorisation>` hiện có**, giữ nguyên namespace, allowlist/connector nếu file sinh ra có những mục đó):

~~~xml
<role-access>
    <match domain="org.apache.activemq.artemis">
        <access method="list*" roles="lab-admin"/>
        <access method="get*" roles="lab-admin"/>
        <access method="is*" roles="lab-admin"/>
        <access method="set*" roles="lab-admin"/>
        <access method="*" roles="lab-admin"/>
    </match>
</role-access>
~~~

Ý nghĩa:

- `domain` xác định miền đối tượng quản trị cần áp dụng quy tắc.
- `list*`, `get*` và `is*` thường là nhóm thao tác đọc; `set*` hoặc wildcard rộng hơn có thể gồm thao tác làm thay đổi trạng thái.
- `roles` là role được cấp trong cơ chế xác thực. Role trong ví dụ phải tồn tại và được gán cho người dùng tương ứng.
- Quy tắc có thể gồm nhiều `match`/`access` với độ cụ thể khác nhau; **không thay cả file bằng đoạn trên** và không tự giả định wildcard một mình thể hiện nguyên tắc ít quyền nhất.

Nếu cần một user chỉ xem trạng thái broker, tách role đọc khỏi role vận hành và xác minh **từng phương thức** mà console/JMX cần. Trong bản cấu hình thực tế, console có thể dùng Jolokia/Hawtio và các cơ chế bảo vệ thêm; việc sửa `management.xml` không thay cho xác thực JAAS, TLS hoặc hạn chế truy cập mạng.

### Ba phạm vi bảo mật dễ nhầm

| Nhu cầu | Nơi xem trước |
|---|---|
| Một user được gửi đến `lab.orders` hay không? | `broker.xml`: `security-settings`, user/role của instance |
| Giao diện console chạy ở cổng nào? | `bootstrap.xml`: `web bind` |
| User được xem/đổi thuộc tính quản trị JMX nào? | `management.xml`: `authorisation / role-access` |
| User đăng nhập được vào broker/console hay không? | `bootstrap.xml` (JAAS domain) cùng `login.config` và kho user/role tương ứng |

## 8. Kiểm chứng cấu hình sau khi khởi động

Sau khi chỉnh cấu hình, nên **dừng broker và chạy lại trong phòng lab** để chắc chắn cả ba tệp đã được nạp. Một số thay đổi Core có thể được hot reload trong điều kiện nhất định, nhưng không nên mặc định mọi thay đổi trong `broker.xml`, `bootstrap.xml` hay `management.xml` đều áp dụng tức thời.

### 8.1. Kiểm tra log

Từ terminal chạy `bin/artemis run`, quan sát:

1. Broker bắt đầu quá trình startup và không có exception phân tích XML.
2. Acceptor cho client và web server bind đúng địa chỉ/cổng đã chọn; không có `Address already in use`.
3. Thư mục `data/` và `log/` có quyền đọc/ghi phù hợp.
4. Các queue/address khai báo hiện diện trong console hoặc công cụ quản trị.

Không dựa vào một chuỗi log cố định: thông điệp log, mức log và tên logger có thể thay đổi giữa các bản phát hành.

### 8.2. Kiểm tra mạng local

Trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 61616
Test-NetConnection -ComputerName 127.0.0.1 -Port 8161
~~~

Trên Linux/macOS, có thể kiểm tra cổng client bằng công cụ phù hợp với hệ điều hành (ví dụ `nc` nếu đã cài):

~~~bash
nc -vz 127.0.0.1 61616
nc -vz 127.0.0.1 8161
~~~

Hai cổng mở **chỉ chứng minh có tiến trình lắng nghe**, chưa chứng minh đăng nhập JMS thành công hay queue đã được tạo. Mở browser tới console (thường `http://127.0.0.1:8161/console`), đăng nhập bằng tài khoản tạo ở bước 4 và xem địa chỉ `lab.orders`.

Nếu console không mở được nhưng JMS vẫn kết nối, kiểm tra `bootstrap.xml` và log web server. Nếu console mở được nhưng JMS báo từ chối kết nối, kiểm tra acceptor trong `broker.xml` thay vì sửa cổng console.

## 9. Java/JMS: gửi và nhận message để thử broker

Phần này xác thực đầu cuối rằng instance đã chạy, cổng client đúng, user có quyền gửi/nhận, queue anycast tồn tại và transaction có thể commit.

### 9.1. Chọn client đúng namespace

Artemis hỗ trợ các dòng client dùng JMS. Ví dụ dưới đây sử dụng **Jakarta JMS** với import `jakarta.jms.*` và artifact Maven `artemis-jakarta-client`.

Thêm dependency vào dự án Java riêng của bạn; khai báo thuộc tính `artemis.version` trong mục `<properties>` của `pom.xml` bằng **một phiên bản client Artemis cụ thể, tương thích** với môi trường đang chạy:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>${artemis.version}</version>
</dependency>
~~~

Đây là mẫu phụ thuộc vào thuộc tính Maven; phải định nghĩa `<artemis.version>` với giá trị thật trước khi build. Ví dụ các dự án cũ dùng namespace `javax.jms` có thể cần dòng artifact khác tương ứng. Không phối hợp nhầm `javax.jms` và `jakarta.jms` trong cùng đoạn mã hoặc cho rằng dependency của ActiveMQ Classic thay thế được client Artemis trong mọi cấu hình.

### 9.2. Chương trình Java kiểm tra queue

Lưu lớp `ArtemisQueueLab` trong dự án thực hành riêng. Cấu hình `ARTEMIS_USER` và `ARTEMIS_PASSWORD` trong environment của tiến trình Java tương ứng với user được tạo ở bước 4; mã không chứa mật khẩu.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class ArtemisQueueLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String QUEUE_NAME = "lab.orders";

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
            (!"send".equals(args[0]) && !"receive".equals(args[0]))) {
            System.err.println("Dùng: ArtemisQueueLab send|receive");
            return;
        }

        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue(QUEUE_NAME);

            if ("send".equals(args[0])) {
                TextMessage message =
                    context.createTextMessage("PrepareShipment:ORD-1001");
                message.setStringProperty(
                    "eventId", UUID.randomUUID().toString());

                context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, message);

                context.commit();
                System.out.println("Đã gửi và commit message: " +
                    message.getJMSMessageID());
            } else {
                Message received = context.createConsumer(queue)
                    .receive(3000);

                if (received == null) {
                    System.out.println("Không có message trong 3 giây.");
                    return;
                }

                try {
                    if (!(received instanceof TextMessage)) {
                        throw new IllegalArgumentException(
                            "Chỉ hỗ trợ TextMessage trong lab");
                    }
                    TextMessage text = (TextMessage) received;
                    System.out.println(
                        "Nhận eventId=" +
                        text.getStringProperty("eventId") +
                        ", body=" + text.getText());

                    // Trong ứng dụng thật: xử lý nghiệp vụ có idempotency.
                    context.commit();
                } catch (Exception error) {
                    context.rollback(); // Cho phép redelivery theo chính sách.
                    throw error;
                }
            }
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường " + name);
        }
        return value;
    }
}
~~~

**Cách dùng:**

1. Khởi động broker từ instance.
2. Thiết lập `ARTEMIS_USER`/`ARTEMIS_PASSWORD` của lab trong cấu hình chạy ứng dụng; không đưa mật khẩu vào source control.
3. Chạy `ArtemisQueueLab` với đối số `send`; phải thấy một message ID sau khi `context.commit()` thành công.
4. Chạy lần nữa với đối số `receive`; phải thấy cùng payload và `eventId`.
5. Kiểm tra queue depth giảm khi consumer commit, hoặc quan sát message còn lại nếu không có consumer nào nhận.

**Vì sao dùng transaction?** Với `JMSContext.SESSION_TRANSACTED`, gửi message hoặc xác nhận nhận message thông qua `commit()`; khi xử lý thất bại, `rollback()` cho phép broker giao lại theo chính sách. Transaction JMS không tự phối hợp nguyên tử với transaction cơ sở dữ liệu bên ngoài. Consumer production cần khóa idempotency để tránh side effect trùng khi xử lý đã hoàn tất nhưng ACK/commit JMS chưa thành công.

**Một chi tiết môi trường:** Ví dụ dùng `String.isBlank()` nên cần Java 11 trở lên; ở đây chọn Java 17 như điều kiện thực hành. Nếu user có thể login console nhưng Java không nhận được message, cần kiểm tra riêng quyền `send`/`consume` trên `lab.orders` và liệu queue đã tồn tại đúng tên.

## 10. Gỡ lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng kiểm tra trước |
|---|---|---|
| `artemis create` không tìm thấy chương trình | Chạy sai `ARTEMIS_HOME` hoặc chưa giải nén đầy đủ | Dùng đúng `bin/artemis`/`bin/artemis.cmd` của bản phân phối |
| Broker không start sau khi sửa XML | XML sai cấu trúc, duplicate section, tham số không được phiên bản hỗ trợ | Xem log startup; hoàn tác phần vừa đổi trong **file instance** |
| `Address already in use: 61616` | Broker khác hoặc tiến trình khác đang dùng cổng | Dừng tiến trình cũ hoặc đổi acceptor |
| Console `8161` không mở | `web bind`, cổng bị chiếm, ứng dụng console không được nạp | Kiểm tra `bootstrap.xml` và log web |
| JMS báo `Connection refused` | Sai URL/cổng; acceptor không mở hoặc chỉ bind địa chỉ khác | Kiểm tra `broker.xml`: `<acceptors>` |
| JMS báo authentication/authorization | User/password không đúng, role không đủ `send`/`consume` | Kiểm tra user/role và `broker.xml`: `security-settings` |
| Kết nối được nhưng queue không thấy message | Sai tên queue, thiếu anycast queue, consumer khác đã lấy | Kiểm tra `<addresses>` và số consumer |
| Client không thỏa thuận được protocol | Acceptor không cho CORE hoặc client/dependency không tương thích | Kiểm tra `protocols=CORE,...` và namespace/version JMS |
| Console đăng nhập được nhưng thao tác quản trị bị từ chối | Quyền phương thức quản trị hoặc policy ứng dụng web | Kiểm tra `management.xml` và role quản trị |
| Message bị giao lại nhiều lần | Consumer rollback, kết nối mất hoặc xử lý lỗi | Kiểm tra code commit, redelivery policy, DLQ và tính idempotent |

Nên lưu một bản sao cấu hình instance trước mỗi thử nghiệm thay đổi phức tạp để có thể quay lại cấu hình lab đã chạy thành công. Không di chuyển data journal bằng tay trong khi broker hoạt động.

## 11. Bảo mật và nguyên tắc vận hành

Tạo instance chỉ là bước đầu. Trong bài lab, các quyết định sau giúp tránh những giả định sai khi chuyển sang môi trường thật:

- **Chặn truy cập ngoài ý muốn:** dùng `127.0.0.1` cho acceptor và web console local. Khi bắt buộc truy cập từ mạng khác, cần thiết kế TLS, firewall, phân quyền và nhật ký truy cập.
- **Không dùng anonymous cho broker có dữ liệu thật:** cấp user theo nhiệm vụ, giới hạn quyền send/consume hoặc quản trị và quản lý secret tách khỏi source code.
- **Không coi `management.xml` là tệp bảo mật duy nhất:** chính sách messaging ở `broker.xml`, JAAS ở `bootstrap.xml`/các tệp xác thực và phân quyền quản trị là các lớp khác nhau.
- **Hiểu persistence:** Artemis có thể ghi journal/paging trong `data/`, nhưng an toàn dữ liệu còn phụ thuộc dung lượng, filesystem, thiết lập sync, backup và HA. Tăng consumer không làm tăng vô hạn năng lực downstream.
- **Giám sát hàng đợi:** theo dõi queue depth, tuổi message, tốc độ enqueue/dequeue, redelivery, DLQ, số consumer, journal/paging và mức sử dụng đĩa.
- **Tách cấu hình khỏi mã ứng dụng:** địa chỉ broker, user, secret, queue và giao thức nên đi qua cấu hình triển khai; không gắn cứng thông tin nhạy cảm vào repository.
- **Đổi cấu hình có kiểm soát:** xác định cấu hình nạp từ instance nào, kiểm chứng trên một instance lab, sau đó mới áp dụng quy trình rollout của hệ thống.

Với ActiveMQ Classic, các tệp cấu hình và mô hình runtime không giống hệt Artemis. Đừng áp dụng máy móc cách đặt `broker.xml`, `bootstrap.xml` và `management.xml` của Artemis sang Classic. Bài này tập trung vào **broker instance Artemis**, dùng Java/JMS để minh họa một phần hoạt động tích hợp message broker trong hệ thống giao tiếp bất đồng bộ.

## 12. Bài tập tự kiểm tra

1. Hai broker instance có chung `ARTEMIS_HOME` có thể chạy đồng thời không? Muốn chạy cùng máy, cần tách những tài nguyên nào?
2. Muốn đổi cổng JMS từ `61616` sang `61626`, bạn sửa file nào? Muốn đổi cổng console từ `8161` sang `8162`, bạn sửa file nào?
3. Trong `broker.xml`, hãy chỉ rõ điểm khác nhau giữa `<anycast>` có queue `lab.orders` và `<multicast/>` trên `lab.events`.
4. Nếu user đăng nhập console thành công nhưng bị từ chối khi gửi message đến `lab.orders`, bước kiểm tra đầu tiên là gì? Vì sao chỉ sửa `management.xml` có thể không giải quyết lỗi?
5. Trong Java/JMS transacted session, chuyện gì có thể xảy ra nếu consumer cập nhật DB thành công rồi JVM chết trước khi `context.commit()`?
6. Hãy nêu đường dẫn đầy đủ tới ba file cấu hình trọng tâm của **instance bạn vừa tạo**; chụp lại các giá trị `web bind`, acceptor và role-access đang có, nhưng không chia sẻ mật khẩu.

**Tiêu chí hoàn thành lab:** một instance Artemis mới được tạo và chạy từ thư mục riêng; ba tệp cấu hình được tìm thấy và phân biệt đúng; `lab.orders` được định tuyến theo anycast; chương trình Java gửi rồi nhận thành công ít nhất một message có xác thực; người học chỉ ra được file cần kiểm tra khi lỗi liên quan JMS, web console hoặc quyền quản trị.

**Kết luận:** `ARTEMIS_HOME` chứa công cụ để tạo broker, `ARTEMIS_INSTANCE` chứa cấu hình và dữ liệu broker cụ thể. Trong instance, **`broker.xml` điều khiển message broker**, **`bootstrap.xml` điều khiển quá trình bootstrap và web**, còn **`management.xml` điều khiển phân quyền thao tác quản trị**. Xác định đúng ba ranh giới này giúp cấu hình queue/topic, kết nối JMS và xử lý sự cố hiệu quả, đồng thời tạo nền tảng cho bài học nâng cao về acknowledgment, transaction, redelivery, DLQ và vận hành broker đáng tin cậy.
