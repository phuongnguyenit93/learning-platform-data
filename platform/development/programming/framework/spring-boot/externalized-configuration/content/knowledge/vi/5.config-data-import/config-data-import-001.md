# Vai trò của spring.config.import và khác biệt với spring.config.location trong Spring Boot

## Mục tiêu

Spring Boot hỗ trợ nạp cấu hình từ nhiều nơi: **application.properties**, **application.yml**, các file theo profile, thư mục bên ngoài JAR và những nguồn cấu hình được tích hợp thêm. Hai thuộc tính có tên gần nhau là **spring.config.import** và **spring.config.location** thường bị nhầm thành hai cách viết tương đương, dẫn đến việc file không được nạp, cấu hình mặc định biến mất hoặc giá trị cuối cùng khác dự đoán.

Bài này giải thích quy trình **Config Data** khi ứng dụng khởi động, vai trò của **spring.config.import**, cách phân biệt nó với **spring.config.location** và **spring.config.additional-location**, cách xác định đường dẫn, thứ tự ưu tiên, profile, xử lý nguồn bị thiếu và những tình huống thường gặp ở triển khai thực tế.

Sau khi học, người đọc có thể:

- Dùng **spring.config.import** để nạp thêm cấu hình từ một file hoặc một nguồn được hỗ trợ.
- Chọn đúng giữa **import**, **location** và **additional-location** theo mục đích triển khai.
- Giải thích file nào được tìm trước, file nào có thể ghi đè giá trị của file khác.
- Phân biệt **classpath:**, **file:**, đường dẫn tương đối và tiền tố **optional:**.
- Biết phải cấu hình **spring.config.location** ở giai đoạn nào, vì sao đặt nó trong application.yml thường không có tác dụng mong đợi.
- Chẩn đoán các lỗi về file không tồn tại, profile, ghi đè thuộc tính và đường dẫn khi chạy bằng JAR hoặc container.

## 1. Config Data là gì?

Trong Spring Boot, **Config Data** là cơ chế tìm, đọc và hợp nhất các tài liệu cấu hình ở thời điểm khởi động sớm. Những tài liệu đó thường là file .properties hoặc .yml/.yaml, nhưng cơ chế này còn có thể tiếp nhận các loại location khác nếu ứng dụng bổ sung bộ giải quyết location phù hợp.

Khi không chỉ định vị trí thay thế, Spring Boot tra cứu các vị trí mặc định của cấu hình ứng dụng, thường bao gồm những nơi như:

- Gốc classpath.
- Thư mục **config/** trong classpath.
- Thư mục làm việc hiện tại.
- Thư mục **config/** bên ngoài ứng dụng.
- Các thư mục con trực tiếp của **config/** bên ngoài, theo quy tắc tìm kiếm mặc định.

Tên file mặc định gắn với **spring.config.name**, thường là **application**. Vì vậy Spring Boot có thể tìm **application.properties**, **application.yml**, các biến thể theo profile như **application-dev.yml** và những cấu hình khác tương ứng với môi trường.

Không nên hình dung quá trình này là một thao tác đọc duy nhất rồi đóng file. Một tài liệu có thể khai báo **spring.config.import** để mở thêm tài liệu khác. Các tài liệu sau đó được đưa vào tập nguồn cấu hình của Spring, với quy tắc ưu tiên nhất định.

Ví dụ một sơ đồ đơn giản:

~~~text
Lệnh khởi động / biến môi trường / thuộc tính JVM
                    |
                    v
       Xác định tên và vị trí Config Data
                    |
                    v
      Nạp application.yml được tìm thấy
                    |
                    +-- spring.config.import --> extra.yml
                    |
                    v
       Tạo các nguồn thuộc tính (PropertySource)
                    |
                    v
          Spring Environment và Binder
                    |
                    v
         Bean ứng dụng nhận cấu hình
~~~

Ở đây, **import** mở rộng tập tài liệu từ một tài liệu đã được tìm thấy. Ngược lại, **location** điều khiển **địa điểm Spring Boot bắt đầu tìm cấu hình**. Đó là điểm khác nhau cốt lõi.

## 2. spring.config.import dùng để làm gì?

**spring.config.import** khai báo các location cấu hình cần nạp thêm khi Spring Boot xử lý một tài liệu Config Data. Nó thường được viết ngay trong application.yml hoặc application.properties.

Ví dụ ứng dụng có:

~~~yaml
# src/main/resources/application.yml
spring:
  application:
    name: order-service
  config:
    import: "optional:file:./config/order-overrides.yml"

order:
  processing:
    timeout: 5s
~~~

File bên ngoài:

~~~yaml
# ./config/order-overrides.yml
order:
  processing:
    timeout: 15s
    retries: 4
~~~

Khi chạy từ thư mục có file **./config/order-overrides.yml**, ứng dụng nạp application.yml rồi xử lý vị trí import đã khai báo. Trong cơ chế Config Data mặc định, tài liệu được import **có ưu tiên cao hơn tài liệu khai báo import**, nên giá trị **order.processing.timeout** từ tài liệu bổ sung có thể thắng giá trị **5s** của tài liệu gốc.

Kết quả kỳ vọng cho hai khóa trong ví dụ:

| Thuộc tính | application.yml | File import | Giá trị có hiệu lực giữa hai tài liệu |
| --- | --- | --- | --- |
| order.processing.timeout | 5s | 15s | **15s** |
| order.processing.retries | Không khai báo | 4 | **4** |

Từ khóa **optional:** được dùng vì file bổ sung là tùy chọn. Nếu nó không tồn tại, ứng dụng vẫn có thể khởi động và sử dụng **5s** cho timeout, miễn không có lỗi cấu hình khác.

Trong file .properties, nội dung tương đương:

~~~properties
spring.application.name=order-service
spring.config.import=optional:file:./config/order-overrides.yml
order.processing.timeout=5s
~~~

Spring Boot hỗ trợ đọc các định dạng file cấu hình tương thích của cơ chế Config Data, vì vậy không bắt buộc file chính và file import phải cùng phần mở rộng.

### 2.1. Import không phải lệnh import của Java

**spring.config.import** là thuộc tính dùng bởi quá trình khởi động Spring Boot, không phải cú pháp **import** của Java hay thao tác nối văn bản hai file.

Spring xử lý mỗi tài liệu dưới dạng Config Data có vị trí và thứ tự ưu tiên. Một file import có thể khai báo trùng tên thuộc tính với file gốc; khi đó quy tắc ưu tiên áp dụng. Việc nạp thêm tài liệu không đồng nghĩa hai cây YAML sẽ được nối bằng thao tác ghép các dòng vào cùng một mapping.

### 2.2. Một tài liệu có thể khai báo nhiều import

Ví dụ:

~~~yaml
spring:
  config:
    import:
      - "classpath:/shared/common.yml"
      - "optional:file:./config/site.yml"
      - "optional:file:./config/local.yml"
~~~

Danh sách này cho phép đưa cấu hình dùng chung, cấu hình theo nơi triển khai và cấu hình cục bộ vào cùng quy trình. Một cú pháp gọn khác trong .properties:

~~~properties
spring.config.import=classpath:/shared/common.yml,optional:file:./config/site.yml,optional:file:./config/local.yml
~~~

Với nhiều import cùng được khai báo, Spring Boot xử lý thứ tự ưu tiên của các tài liệu được nạp; trong trường hợp những import này đều định nghĩa cùng khóa, **import được liệt kê sau có thể ghi đè import trước** theo quy tắc Config Data thông thường.

Một location đã được import có thể chỉ được nạp một lần ngay cả khi được khai báo lặp. Vì vậy, không dựa vào việc lặp lại cùng location để ép Spring “nạp lần hai” ở một vị trí ưu tiên mới.

### 2.3. Một tài liệu được import vẫn có thể khai báo import tiếp

Ví dụ:

~~~text
application.yml
  |
  +-- import: ./config/common.yml
                    |
                    +-- import: feature.yml
~~~

Điều này tạo ra chuỗi phụ thuộc cấu hình. Với cấu hình lớn, nên giữ chuỗi này ngắn, dễ truy nguyên và có quy ước sở hữu file. Người vận hành cần biết file nào là điểm bắt đầu và file nào được tài liệu khác tham chiếu, thay vì phải đoán các file tự động được quét ở đâu.

## 3. Phân biệt import, location và additional-location

Ba thuộc tính giải quyết ba nhu cầu riêng:

| Thuộc tính | Vai trò | Thường khai báo ở đâu? | Ảnh hưởng đến vị trí mặc định? |
| --- | --- | --- | --- |
| **spring.config.import** | Nạp thêm tài liệu từ location được tài liệu hiện tại khai báo | application.yml, application.properties hoặc tài liệu Config Data khác | Không tự thay tập vị trí mặc định |
| **spring.config.location** | Chỉ định tập location dùng để tìm Config Data khi bắt đầu khởi động | Biến môi trường, JVM system property hoặc tham số dòng lệnh | **Thay thế** tập location mặc định |
| **spring.config.additional-location** | Cộng thêm các location tìm kiếm vào tập mặc định | Biến môi trường, JVM system property hoặc tham số dòng lệnh | **Giữ** các location mặc định và bổ sung vị trí mới |

Sơ đồ so sánh:

~~~text
Mặc định:
  [Vị trí tìm cấu hình mặc định] --> application.yml

Có spring.config.import trong application.yml:
  [Vị trí mặc định] --> application.yml --> file được import

Có spring.config.location lúc khởi động:
  [Vị trí chỉ định bằng location] --> các file tại vị trí ấy

Có spring.config.additional-location lúc khởi động:
  [Vị trí mặc định + vị trí bổ sung] --> các tài liệu tìm thấy
~~~

### 3.1. Khi nào chọn import?

Dùng **spring.config.import** khi một tài liệu đã được nạp **cần phụ thuộc vào hoặc mở rộng bằng** cấu hình khác.

Ví dụ:

- application.yml luôn khai báo import một file bổ sung cho module billing.
- Cấu hình theo profile cần nạp tệp cấu hình của một tích hợp cụ thể.
- Một file cấu hình import cây cấu hình được gắn vào container.
- Ứng dụng dùng một resolver được cài thêm, cho phép import nguồn cấu hình đặc thù.

Điểm lợi là quan hệ phụ thuộc nằm ngay trong file cấu hình chính. Người đọc application.yml thấy được ứng dụng còn cần nạp thêm gì.

### 3.2. Khi nào chọn location?

Dùng **spring.config.location** khi người vận hành cần quyết định ứng dụng **chỉ tìm file cấu hình ở tập vị trí được cung cấp**, thay cho mặc định.

Ví dụ:

~~~bash
java -jar demo.jar --spring.config.location=optional:file:./deployment/application.yml
~~~

Ở đây, tập location mặc định được thay thế. Không nên kỳ vọng file application.yml đóng gói sẵn trong JAR vẫn tự động được nạp nếu nó không nằm trong tập location mới và cũng không được một tài liệu đã nạp import trở lại.

Điều này có thể hữu ích khi môi trường triển khai quản lý toàn bộ cấu hình như một gói độc lập. Nhưng nếu ứng dụng dựa vào giá trị mặc định trong classpath, đổi **location** không cẩn thận có thể làm các giá trị đó biến mất.

### 3.3. Khi nào chọn additional-location?

Dùng **spring.config.additional-location** khi muốn **giữ cấu hình đóng gói trong JAR** và cho phép môi trường triển khai thêm hoặc ghi đè một số thuộc tính:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./deployment/
~~~

Dấu **/** cuối cho biết đây là directory location. Spring Boot sử dụng tên cấu hình đang có hiệu lực, thông thường **application**, để tìm file trong thư mục.

Các file ở additional-location có thể ghi đè cấu hình mặc định theo quy tắc ưu tiên giữa các location. Cách này rất phù hợp cho một JAR dùng chung nhiều môi trường: gói JAR có default, còn đường dẫn triển khai chứa override.

## 4. Vì sao location phải được thiết lập từ sớm?

Hãy xét ý tưởng sau:

~~~yaml
# src/main/resources/application.yml
spring:
  config:
    location: "file:./my-runtime/"
~~~

Mục tiêu của người viết là yêu cầu Spring Boot tìm cấu hình ở **my-runtime/**. Nhưng đây là một vòng phụ thuộc: để đọc được giá trị **spring.config.location**, Spring phải tìm và nạp **application.yml** trước; trong khi chính **location** lại quyết định nơi tìm application.yml.

Vì vậy **spring.config.location**, **spring.config.additional-location** và **spring.config.name** là các thuộc tính điều khiển quá trình tìm kiếm từ rất sớm. Chúng cần được cung cấp **trước khi Config Data được nạp**, thường qua:

- Tham số ứng dụng: **--spring.config.location=...**
- JVM system property: **-Dspring.config.location=...**
- Biến môi trường: **SPRING_CONFIG_LOCATION=...**

Ví dụ đúng:

~~~bash
java -Dspring.config.location=optional:file:./my-runtime/ -jar demo.jar
~~~

Hoặc:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:./deployment/ java -jar demo.jar
~~~

Trên Windows PowerShell:

~~~powershell
$env:SPRING_CONFIG_ADDITIONAL_LOCATION = "optional:file:./deployment/"
java -jar demo.jar
~~~

Trái lại, **spring.config.import** được thiết kế để khai báo *bên trong* một tài liệu Config Data mà Spring đã tìm thấy, rồi mở rộng quá trình nạp. Đây là lý do hai thuộc tính này được đặt tại những thời điểm khác nhau trong vòng đời khởi động.

## 5. Location trỏ đến file hay thư mục?

Một location có thể mô tả file cụ thể hoặc thư mục tìm kiếm. Phân biệt này quan trọng nhất với **spring.config.location** và **spring.config.additional-location**.

### 5.1. Chỉ rõ một file

~~~bash
java -jar demo.jar --spring.config.location=optional:file:./deployment/worker.yml
~~~

Vị trí này chỉ tới một file với tên rõ ràng. Nếu đường dẫn tồn tại, Spring Boot có thể đọc file phù hợp. Nếu khai báo nhiều file hoặc group location, mỗi location được xử lý theo cơ chế ưu tiên tương ứng.

### 5.2. Chỉ rõ một thư mục

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./deployment/
~~~

Vì location kết thúc bằng **/**, đây là thư mục. Spring Boot sẽ kết hợp với **spring.config.name** để tìm các tên như **application.properties** hoặc **application.yml**, cùng biến thể profile khi áp dụng.

Nếu dùng:

~~~bash
java -jar demo.jar --spring.config.name=myapp --spring.config.additional-location=optional:file:./deployment/
~~~

Spring Boot tìm tên cấu hình **myapp** tương ứng, không phải bất kỳ tên file ngẫu nhiên nào trong thư mục. Thư mục chứa **custom.yml** sẽ không được nạp chỉ vì nó nằm trong **deployment/**, trừ khi tên tìm kiếm hoặc một khai báo import/location khác trỏ đến file ấy.

### 5.3. Dấu phẩy và dấu chấm phẩy trong location

Spring Boot cho phép khai báo nhiều location khi thiết lập đường dẫn. Dấu **,** thường phân tách các location theo thứ tự; dấu **;** biểu diễn một **location group**, trong đó các vị trí được xem cùng cấp để xét thứ tự ưu tiên cấu hình profile.

Ví dụ mô tả hai kiểu khai báo:

~~~text
classpath:/defaults/,file:./deployment/
classpath:/defaults/;file:./deployment/
~~~

Hai chuỗi có thể tạo thứ tự ưu tiên khác nhau khi tồn tại file theo profile ở nhiều vị trí. Khi một nhóm location phức tạp ảnh hưởng đến kết quả, cần xem cả **spring.config.name**, các profile đang active và thứ tự group thay vì chỉ đọc thứ tự file thông thường.

Trong shell, dấu **;** có thể là ký tự điều khiển lệnh. Hãy đặt giá trị tham số trong dấu nháy phù hợp với shell để tránh cắt lệnh ngoài ý muốn.

## 6. Cách giải quyết đường dẫn cho spring.config.import

Khi khai báo import, cần phân biệt **fixed location** và **import-relative location**.

### 6.1. Fixed location

Một location bắt đầu bằng sơ đồ rõ ràng như **classpath:** hoặc **file:** được coi là fixed location.

~~~yaml
spring:
  config:
    import:
      - "classpath:/shared/settings.yml"
      - "optional:file:./deployment/extra.yml"
~~~

- **classpath:/shared/settings.yml** trỏ tới tài nguyên trong classpath ứng dụng, theo đường dẫn đã chỉ định.
- **file:./deployment/extra.yml** là đường dẫn file tương đối với thư mục làm việc của tiến trình, với tiền tố nhận diện **file:**; trong các tình huống triển khai, working directory cần được xác định rõ.
- **optional:** cho phép bỏ qua một location không tồn tại mà lẽ ra có thể gây lỗi khi nạp.

Không mặc định hiểu **file:./...** là “tương đối với file application.yml trong JAR”. Đường dẫn hệ thống file không tự nằm cùng thư mục với tài nguyên classpath.

### 6.2. Import-relative location

Khi không có sơ đồ hoặc ký hiệu location cố định, một import có thể được giải quyết **tương đối với tài liệu khai báo nó**.

Ví dụ, file:

~~~text
classpath:/features/application.properties
~~~

chứa:

~~~properties
spring.config.import=feature-flags.properties
~~~

Khi đó location **feature-flags.properties** có thể được giải quyết tương đối với file khai báo, tương ứng với tài nguyên ở cùng khu vực:

~~~text
classpath:/features/feature-flags.properties
~~~

Tương tự, nếu một file ngoài JAR khai báo import tương đối, vị trí của file đang khai báo import sẽ tham gia vào cách xác định đường dẫn đích.

Quy tắc thực hành: **dùng đường dẫn tương đối để giữ hai file cấu hình đi cùng nhau; dùng classpath: hoặc file: khi muốn vị trí đích được nêu tường minh**. Đừng trộn lẫn hai ý nghĩa này trong cùng một ví dụ rồi suy diễn theo working directory.

### 6.3. Location không có phần mở rộng

Một số hệ thống triển khai gắn file cấu hình với tên không có đuôi, chẳng hạn **/etc/myapp/config**. Spring Boot có thể dùng **extension hint** để biết định dạng:

~~~properties
spring.config.import=file:/etc/myapp/config[.yaml]
~~~

Phần **[.yaml]** hướng dẫn bộ nạp xử lý nội dung như YAML; đây không phải yêu cầu đổi tên file trên hệ thống. Nếu file được gắn từ Secret hoặc ConfigMap mà extension không có, cơ chế này có thể cần thiết.

Cần phân biệt extension hint của file đơn lẻ với cách nạp **configtree:** từ một directory, được trình bày ở phần sau.

## 7. Optional và cách xử lý location bị thiếu

Không phải location nào cũng có cùng mức bắt buộc.

### 7.1. Import bắt buộc

~~~yaml
spring:
  config:
    import: "file:./config/service.yml"
~~~

Nếu file không tồn tại hoặc location không thể được tìm thấy theo cơ chế nạp tương ứng, Spring Boot có thể dừng khởi động với lỗi thuộc nhóm **ConfigDataLocationNotFoundException** hoặc thông báo liên quan đến location không tìm thấy.

Một lỗi đường dẫn tại startup khác với “ứng dụng vẫn chạy nhưng giá trị rỗng”: ở tình huống này, quá trình nạp Config Data có thể không hoàn tất.

### 7.2. Import tùy chọn

~~~yaml
spring:
  config:
    import: "optional:file:./config/service.yml"
~~~

Nếu file không tồn tại, Spring Boot có thể bỏ qua location đó. Những cấu hình đã được nạp từ nguồn khác vẫn được giữ.

**optional:** chỉ giải quyết trường hợp location bị thiếu theo quy tắc được hỗ trợ. Nó **không có nghĩa** mọi lỗi nội dung YAML, lỗi parse, lỗi bind, lỗi xác thực với dịch vụ từ xa hoặc lỗi truy cập đều được nuốt đi. Không dùng optional để che các cấu hình mà hệ thống bắt buộc phải có.

### 7.3. Áp dụng optional cho location

Ví dụ:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./site-config/
~~~

Nếu thư mục **site-config/** không tồn tại, ứng dụng vẫn có thể tiếp tục với các cấu hình mặc định. Điều này phù hợp với môi trường phát triển không có tệp triển khai riêng.

Với môi trường production, hãy cân nhắc liệu cấu hình ngoài có bắt buộc hay không. Nếu file chứa địa chỉ dịch vụ hoặc thiết lập bảo mật thiết yếu, bỏ optional có thể giúp lỗi xuất hiện sớm, ngay khi triển khai sai.

Có thể gặp **spring.config.on-not-found=ignore** để thay đổi cách xử lý chung khi không tìm thấy Config Data; đây là thiết lập diện rộng, không nên bật chỉ để tránh sửa một đường dẫn import sai.

## 8. Thứ tự ưu tiên khi một tài liệu import tài liệu khác

Đây là nguồn gây nhầm lẫn phổ biến. Xét hai file:

~~~yaml
# application.yml
spring:
  config:
    import: "classpath:/config/extra.yml"

demo:
  mode: standard
  timeout: 10s
~~~

~~~yaml
# config/extra.yml trong classpath
demo:
  mode: enhanced
  retries: 3
~~~

Với hai tài liệu trên, file được import có ưu tiên cao hơn tài liệu khai báo import đối với khóa trùng. Kết quả từ Config Data:

~~~properties
demo.mode=enhanced
demo.timeout=10s
demo.retries=3
~~~

Vì import được chèn theo quy tắc ưu tiên của tài liệu Config Data, **vị trí vật lý của dòng spring.config.import ở đầu hay cuối file không quyết định thắng-thua**. Không cần chuyển dòng import lên trước demo.mode để mong thay đổi kết quả.

Bây giờ có thêm tham số ứng dụng:

~~~bash
java -jar demo.jar --demo.mode=cli
~~~

Trong thứ tự nguồn chuẩn, command-line property có mức ưu tiên cao hơn Config Data; **demo.mode** lúc này là **cli**. Vì vậy câu “import thắng file gốc” chỉ mô tả quan hệ giữa các tài liệu Config Data đang xét, **không có nghĩa file import thắng mọi nguồn khác của Spring Environment**.

### 8.1. Nhiều import cùng khai báo

~~~properties
spring.config.import=classpath:/config/base-extra.properties,classpath:/config/team-extra.properties
~~~

Nếu cả hai tài liệu đều chứa **demo.mode**, tài liệu import sau có thể có ưu tiên cao hơn tài liệu import trước. Hãy giữ thứ tự thể hiện rõ ý định: từ cấu hình chung đến cấu hình đặc thù của môi trường hoặc nhóm.

Khi dự án có nhiều tài liệu theo profile hoặc location group, thứ tự thực tế phức tạp hơn ví dụ hai file. Khi debug, hãy xác định danh sách tài liệu được nạp và xem nguồn có độ ưu tiên cao nhất chứa khóa đó.

### 8.2. Import không hợp nhất danh sách như phép cộng

Nếu file gốc và file import đều khai báo một list, đừng mặc định list trong file import sẽ được nối vào cuối list của file gốc.

Ví dụ:

~~~yaml
# application.yml
app:
  nodes:
    - alpha
    - beta
~~~

~~~yaml
# extra.yml
app:
  nodes:
    - gamma
~~~

Khi binding list từ các nguồn Config Data, quy tắc Spring Boot thường xem danh sách từ nguồn ưu tiên cao là danh sách áp dụng, thay vì cộng từng phần tử theo cách gộp YAML thủ công. Nếu muốn ba phần tử, khai báo cả ba trong nguồn thắng hoặc thiết kế cơ chế hợp nhất riêng trong ứng dụng.

Với Map, quy tắc binding lại có thể kết hợp các khóa khác nhau từ nhiều nguồn. Vì vậy không suy diễn cách xử lý cấu trúc nested, list và map chỉ từ ví dụ một scalar.

## 9. Import và profile

Spring Boot hỗ trợ các file theo profile như **application-dev.yml**, **application-prod.properties** và các tài liệu YAML có điều kiện **spring.config.activate.on-profile**.

Ví dụ:

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:./config/payment.yml"
payment:
  mode: sandbox
~~~

Nếu profile **prod** được kích hoạt, cơ chế Config Data còn có thể xét các biến thể theo profile của những location được import, chẳng hạn **payment-prod.yml** nếu có và được hỗ trợ ở vị trí tương ứng.

File import thường:

~~~yaml
# config/payment.yml
payment:
  timeout: 2s
  endpoint: "https://sandbox.example.test"
~~~

Biến thể profile:

~~~yaml
# config/payment-prod.yml
payment:
  timeout: 5s
  endpoint: "https://payments.example.test"
~~~

Khi profile prod hoạt động, cần xét thêm tài liệu theo profile để xác định giá trị cuối cùng. Đừng chỉ đọc payment.yml rồi kết luận rằng timeout luôn là 2s.

### 9.1. Import trong tài liệu có điều kiện kích hoạt

Một file YAML có thể chia thành nhiều tài liệu bằng dấu **---**:

~~~yaml
spring:
  application:
    name: demo
demo:
  stage: default

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:file:./config/dev-overrides.yml"
demo:
  stage: development
~~~

Tài liệu thứ hai chỉ áp dụng khi điều kiện profile phù hợp. Do đó import thuộc tài liệu ấy có thể chỉ được xử lý khi profile dev được kích hoạt.

Tình huống này khác với việc đặt **spring.config.location** trong tài liệu profile: location quyết định bước tìm file ban đầu nên không nên được đưa vào một tài liệu chỉ có thể biết sau khi bước tìm file đã diễn ra.

### 9.2. Active profile phải được biết đúng thời điểm

Thông thường có thể kích hoạt profile bằng tham số:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

Hoặc biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
~~~

Profile đang hoạt động ảnh hưởng các tài liệu config data được chọn; import trong tài liệu được kích hoạt cũng có thể đưa thêm cấu hình vào ứng dụng.

Không dùng **spring.profiles.active** trong tài liệu chỉ dành riêng cho profile hay tài liệu kích hoạt bằng **spring.config.activate.on-profile**; Spring Boot có ràng buộc về nơi có thể khai báo thuộc tính kích hoạt profile. Thiết kế rõ ràng hơn là dùng tham số khởi động hoặc tài liệu nền không phụ thuộc profile để xác định profile.

## 10. Import configtree từ thư mục gắn vào container

Một trường hợp đặc biệt là **configtree:**. Thay vì đọc một file YAML chứa nhiều khóa, Spring Boot có thể coi các file trong một directory như các mục cấu hình.

Giả sử hệ thống triển khai gắn directory:

~~~text
/run/secrets/service/
├── username
└── password
~~~

Trong đó file **username** chứa tên tài khoản và file **password** chứa mật khẩu. Có thể khai báo:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/service/"
~~~

Spring Boot dùng cơ chế config tree để đưa những mục tương ứng vào Environment. Đây là cách quen thuộc khi triển khai trên nền tảng gắn Secret hay ConfigMap thành từng file.

Nếu muốn các tên thuộc tính có prefix rõ ràng, hãy bố trí cấu trúc directory tương ứng hoặc khai báo đường dẫn configtree theo quy tắc nền tảng thực tế. Không giả định tên **username** trong cây file sẽ tự biến thành **spring.datasource.username** nếu không có cấu trúc hoặc mapping phù hợp.

**configtree:** khác với:

~~~yaml
spring:
  config:
    import: "file:/run/secrets/service/"
~~~

Đường dẫn thứ hai chỉ dùng **file:** trỏ tới thư mục, không nói rằng từng file bên trong phải trở thành một property. Nếu muốn đọc cây cấu hình, phải sử dụng prefix **configtree:** và cấu trúc thư mục phù hợp.

Đừng đưa dữ liệu secret thật vào ví dụ, commit hoặc log. Việc Config Data đọc được secret không thay thế yêu cầu giới hạn quyền truy cập file và endpoint quản trị.

## 11. Import nguồn cấu hình từ xa

**spring.config.import** không bị giới hạn về mặt ý tưởng chỉ ở file trong JAR và file trên ổ đĩa. Spring Boot có cơ chế mở rộng **ConfigDataLocationResolver** và **ConfigDataLoader** để những tích hợp khác cung cấp cách nạp Config Data.

Ví dụ, trong một ứng dụng đã cài đặt **Spring Cloud Config Client** với phiên bản tương thích, có thể gặp:

~~~properties
spring.config.import=optional:configserver:
~~~

Prefix **configserver:** không phải một URL/file import mặc định của mọi ứng dụng Spring Boot thuần. Nó cần thư viện và cơ chế tích hợp phù hợp. Nếu thiếu dependency cần thiết, chỉ thêm dòng import sẽ không tự tạo ra kết nối tới config server.

Tương tự, các prefix dành cho hệ thống quản lý secret hoặc cấu hình ngoài chỉ hoạt động khi project có resolver/loader tương ứng.

Điểm cần hiểu là:

- **Import** chỉ ra một nguồn dữ liệu bổ sung theo giao thức location mà ứng dụng hiểu.
- **Location** chọn các vị trí tìm Config Data ban đầu.
- Một prefix ngoài khả năng của project có thể gây lỗi về location hoặc resolver, không phải lỗi do .properties hay YAML thiếu dấu nháy.

Nếu một nguồn từ xa là bắt buộc, hãy xác định rõ cách ứng dụng phản ứng khi không kết nối được. Tiền tố optional không có cùng ý nghĩa cho mọi loại lỗi mạng, xác thực hoặc định dạng.

## 12. Tình huống so sánh thực tế

Giả sử JAR đóng gói:

~~~yaml
# classpath:/application.yml
app:
  banner: "bundled"
  timeout: 4s
~~~

Và máy triển khai có file:

~~~yaml
# ./deployment/application.yml
app:
  banner: "deployed"
  retries: 3
~~~

### Tình huống A: dùng spring.config.location

~~~bash
java -jar demo.jar --spring.config.location=file:./deployment/
~~~

File từ vị trí chỉ định được tìm và nạp. Vì tập location mặc định bị thay thế, không thể dựa vào mặc định **timeout: 4s** của file classpath. Nếu cấu hình ngoài thiếu timeout và không có nguồn nào khác khai báo, thuộc tính này có thể không được cung cấp.

Phương án này phù hợp khi file triển khai quản lý cấu hình như một tập độc lập hoàn chỉnh.

### Tình huống B: dùng spring.config.additional-location

~~~bash
java -jar demo.jar --spring.config.additional-location=file:./deployment/
~~~

Các vị trí mặc định vẫn được giữ và vị trí deployment được bổ sung. Theo quy tắc ưu tiên thông thường giữa các vị trí này, cấu hình ngoài có thể ghi đè **app.banner** thành **deployed**, trong khi **app.timeout** vẫn nhận **4s** nếu không bị nguồn nào khác thay thế.

Phương án này phù hợp khi muốn sử dụng default trong JAR và override theo môi trường.

### Tình huống C: dùng spring.config.import trong application.yml

Thay file đóng gói thành:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment/application.yml"
app:
  banner: "bundled"
  timeout: 4s
~~~

Không cần truyền location lúc khởi động. File đóng gói được tìm qua cơ chế mặc định, sau đó khai báo import khiến file triển khai được nạp thêm. Trong mối quan hệ giữa hai tài liệu, file import được ưu tiên cho **app.banner**, còn **app.timeout** giữ từ file gốc.

Phương án này cho phép chính ứng dụng nêu rõ việc nó hỗ trợ một file cấu hình bổ sung. Nếu file import là bắt buộc, bỏ **optional:**.

### Tình huống D: thêm tham số command line

Dù chọn phương án B hoặc C, một lệnh như:

~~~bash
java -jar demo.jar --app.banner=command-line
~~~

có thể khiến **app.banner** nhận **command-line**, vì tham số ứng dụng thường ưu tiên cao hơn các tài liệu Config Data. Đừng nhầm thứ tự ưu tiên giữa file gốc và file import với toàn bộ thứ tự PropertySource của Spring.

## 13. Các lỗi thường gặp và cách nhận diện

### 13.1. Không tìm thấy file import

**Biểu hiện:** ứng dụng dừng khi khởi động với thông báo không tìm thấy location.

**Kiểm tra:** đường dẫn, phần mở rộng .yml/.yaml/.properties, working directory, classpath thực tế, chữ hoa/chữ thường trên hệ điều hành và có dùng **optional:** đúng mục đích không.

**Ví dụ:**

~~~yaml
spring:
  config:
    import: "file:./config/runtime.yml"
~~~

Nếu chạy JAR từ một thư mục khác, **./config/runtime.yml** có thể không trỏ tới nơi tưởng tượng. Trước khi thay bằng optional, xác định vị trí thật của file.

### 13.2. File mặc định không còn được nạp

**Biểu hiện:** hàng loạt giá trị từng có trong application.yml mất đi sau khi thay lệnh khởi động.

**Kiểm tra:** có dùng **spring.config.location** để chỉ định một file/thư mục mới không. Vì location thay thế tập mặc định, hãy cân nhắc đổi thành **spring.config.additional-location** nếu mục tiêu thực tế chỉ là override.

### 13.3. Đặt spring.config.location trong application.yml

**Biểu hiện:** người viết thấy thuộc tính trong file nhưng Spring không tìm cấu hình theo đường dẫn đó.

**Giải thích:** thuộc tính điều khiển tìm kiếm cần có trước bước nạp file. Truyền location qua tham số dòng lệnh, biến môi trường hoặc JVM system property.

### 13.4. Import một file trống hoặc chứa khóa sai

**Biểu hiện:** ứng dụng vẫn chạy nhưng giá trị mong đợi không đổi.

**Kiểm tra:** file có đúng tên khóa hay không, YAML có đúng cấp thụt lề không, tài liệu theo profile có được kích hoạt không, và có nguồn ưu tiên cao hơn ghi đè không. Import thành công không đồng nghĩa mọi thuộc tính trong file đều hợp lệ với bean đích.

### 13.5. Import lặp ở nhiều nơi

**Biểu hiện:** tưởng rằng khai báo cùng file import hai lần sẽ cho hai lớp override.

**Giải thích:** Config Data tránh import cùng một location nhiều lần. Nếu cần hai bộ giá trị độc lập, tạo hai location khác nhau với thứ tự và trách nhiệm rõ ràng.

### 13.6. Nhầm thư mục với file trong location

**Biểu hiện:** chỉ định **file:./deployment** để tìm **application.yml** bên trong nhưng không đạt kết quả.

**Hướng xử lý:** nếu là directory location, ghi rõ dấu **/** cuối như **file:./deployment/**. Nếu là file, chỉ ra tên file và phần mở rộng cụ thể.

### 13.7. Nhầm path tương đối với file khai báo

**Biểu hiện:** file import nằm cạnh một file cấu hình ngoài nhưng chương trình tìm ở một vị trí khác.

**Hướng xử lý:** phân biệt **import-relative** (không có prefix cố định) với **file:./...** (đường dẫn file theo working directory), và dùng một kiểu thống nhất phù hợp với cách đóng gói.

### 13.8. Một giá trị chỉ sai ở profile production

**Biểu hiện:** giá trị đúng ở dev nhưng khác ở prod.

**Kiểm tra:** profile đang hoạt động, tài liệu **spring.config.activate.on-profile**, file theo profile của location import và thứ tự group/location. Cũng cần kiểm tra biến môi trường và command-line argument riêng của môi trường production.

### 13.9. Đường dẫn đã tìm thấy nhưng YAML bị lỗi

**Biểu hiện:** ứng dụng báo lỗi YAML parser hoặc lỗi bind sau khi import.

**Giải thích:** **optional:** không chữa được nội dung file lỗi. Hãy sửa cú pháp YAML, khóa trùng, sai kiểu dữ liệu hoặc kiểu đích của @ConfigurationProperties.

## 14. Cách chẩn đoán Spring Boot đang dùng cấu hình nào

Khi giá trị runtime khác dự kiến, hãy làm theo quy trình cụ thể:

1. **Ghi tên thuộc tính cần kiểm tra**, ví dụ **app.timeout**.
2. **Ghi lại đúng lệnh khởi chạy**: có **--spring.config.location**, **--spring.config.additional-location** hoặc **--spring.config.name** không?
3. **Xác định file ban đầu Spring có thể tìm thấy** theo location được chỉ định hoặc các vị trí mặc định.
4. **Đọc các spring.config.import trong những file được nạp**, theo các nhánh phụ thuộc liên quan.
5. **Kiểm tra profile**, tài liệu YAML kích hoạt theo profile và file biến thể theo profile.
6. **Xác định nguồn ưu tiên cao hơn**, như command-line args, JVM system properties hoặc biến môi trường.
7. **Đọc kết quả Spring Environment hoặc bean cấu hình**, tránh kết luận chỉ từ file.

Đoạn mã minh họa chỉ đọc một property thông thường:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigDataProbe implements ApplicationRunner {
    private final Environment environment;

    ConfigDataProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("app.timeout = "
                + environment.getProperty("app.timeout"));
    }
}
~~~

Kết quả **Environment.getProperty(...)** cho biết giá trị mà hệ thống phân giải cấu hình Spring nhìn thấy tại thời điểm gọi. Nó không tự cho biết file nguồn; để tìm provenance cần xem các PropertySource hoặc công cụ chẩn đoán tương ứng.

Một ví dụ liệt kê tên các nguồn:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

ConfigurableEnvironment env = /* môi trường Spring đã được cung cấp */;
for (PropertySource<?> source : env.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

Trong code thực tế, có thể inject **ConfigurableEnvironment** vào một bean phù hợp, rồi duyệt theo cách trên. Không in toàn bộ nội dung PropertySource vào log: file import và configtree có thể chứa bí mật triển khai.

Nếu đã dùng Spring Boot Actuator và được cấu hình bảo vệ, endpoint env có thể giúp quan sát thuộc tính và nguồn; dữ liệu nhạy cảm có thể bị che. Không mở endpoint quản trị công khai chỉ để kiểm tra một dòng import.

### 14.1. Quan sát quá trình nạp Config Data

Ở môi trường phát triển, có thể điều chỉnh mức log cho nhóm xử lý Config Data khi cần hiểu trình tự nạp file. Tên logger cụ thể có thể thay đổi theo phiên bản Spring Boot, nên ưu tiên xác minh bằng log thực tế và thông tin trong phiên bản đang chạy.

Ghi chú thêm rằng **logging.config** và các thuộc tính điều khiển khởi động rất sớm có những đặc điểm vòng đời riêng; tránh đặt chúng vào nguồn chỉ được nạp sau khi hệ thống đã cần dùng đến chúng.

## 15. Bài thực hành: chọn đúng cơ chế

### Bài 1: Giữ mặc định trong JAR và ghi đè ở deployment

Yêu cầu: ứng dụng có application.yml với timeout mặc định, môi trường production cần ghi đè một số khóa mà không phải sửa JAR.

Lệnh phù hợp:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./deployment/
~~~

Cách khác: nếu muốn ứng dụng tự mô tả file bổ sung, khai báo một **spring.config.import** phù hợp trong application.yml. Cả hai có thể giữ cấu hình cơ sở; khác nhau ở nơi quy định quan hệ nạp.

Không chọn **spring.config.location** chỉ vì muốn “thêm một file”: nó thay thế các vị trí tìm mặc định.

### Bài 2: Tập cấu hình ngoài JAR là nguồn duy nhất

Yêu cầu: khi chạy JAR, chỉ sử dụng các file configuration ở một thư mục quản lý tập trung, không dựa vào các file application.yml mặc định trong JAR.

Lệnh minh họa:

~~~bash
java -jar demo.jar --spring.config.location=file:./managed-config/
~~~

Với directory này, tên file được tìm phụ thuộc **spring.config.name** và profile. Nếu cần giữ một file mặc định nào đó từ JAR, phải bổ sung rõ vào tập location hoặc cấu hình import thích hợp.

### Bài 3: Chỉ import khi có file override

~~~yaml
spring:
  config:
    import: "optional:file:./local-overrides.yml"
demo:
  feature-enabled: false
~~~

Nếu file local-overrides.yml không tồn tại, ứng dụng có thể tiếp tục dùng **demo.feature-enabled=false**. Nếu file tồn tại và khai báo true, giá trị import có thể thắng file khai báo. Nếu command line khai báo **--demo.feature-enabled=false**, giá trị command line vẫn có thể thắng các file theo thứ tự nguồn mặc định.

### Bài 4: Phân tích precedence

Các nguồn đang tồn tại:

~~~yaml
# application.yml
spring:
  config:
    import: "classpath:/extra.yml"
demo:
  retries: 1
~~~

~~~yaml
# extra.yml
demo:
  retries: 2
~~~

Và ứng dụng được chạy bằng:

~~~bash
DEMO_RETRIES=3 java -Ddemo.retries=4 -jar demo.jar --demo.retries=5
~~~

Theo cơ chế nguồn chuẩn trong ví dụ, các giá trị ứng viên lần lượt là **1**, **2**, **3**, **4**, **5**, và giá trị có hiệu lực là **5**. Nếu bỏ tham số command line, JVM system property **4** thắng; nếu bỏ tiếp **-D**, biến môi trường **3** thắng; nếu bỏ cả biến môi trường, tài liệu import **2** thắng tài liệu gốc **1**.

Bài này cho thấy import có độ ưu tiên của riêng nó trong Config Data, nhưng vẫn nằm trong toàn bộ thứ tự PropertySource của Spring Boot.

## 16. Bảng quyết định nhanh

| Bạn muốn làm gì? | Cơ chế nên cân nhắc | Vì sao |
| --- | --- | --- |
| File application.yml cần kéo thêm một file cụ thể | **spring.config.import** | Quan hệ phụ thuộc được khai báo ngay trong tài liệu |
| Cấu hình triển khai cần thêm vào default của JAR | **spring.config.additional-location** | Giữ vị trí mặc định và cho phép override |
| Thay toàn bộ nơi Spring tìm cấu hình mặc định | **spring.config.location** | Tập vị trí tìm kiếm được thay thế |
| Đổi basename từ application thành custom | **spring.config.name** | Điều khiển tên file khi tìm trong directory |
| File import có thể không tồn tại trên máy dev | **optional:** trên location cụ thể | Không dừng vì location thiếu |
| Import từng file secret trong một directory | **configtree:** | Đưa các file trong cây thành thuộc tính |
| Import nguồn cấu hình do thư viện khác hỗ trợ | **spring.config.import** với resolver tương ứng | Cơ chế nạp được mở rộng bằng dependency |
| Muốn thay đổi config theo profile | Profile-specific file hoặc tài liệu activate.on-profile | Giữ tách biệt cấu hình theo môi trường |
| Muốn biết giá trị thật lúc chạy | Spring Environment và PropertySource | Cho thấy kết quả sau khi áp dụng precedence |

## 17. Những điểm cần ghi nhớ

**spring.config.import** giúp một tài liệu Config Data nạp thêm tài liệu khác, và tài liệu được import thường có ưu tiên cao hơn tài liệu khai báo nó. Nó phù hợp để mô tả phụ thuộc cấu hình trực tiếp trong application.yml hoặc application.properties.

**spring.config.location** điều khiển tập vị trí tìm Config Data khi khởi động; nó **thay thế** các vị trí mặc định. Thuộc tính này phải được cung cấp ở giai đoạn khởi động sớm, thường qua CLI, JVM system property hoặc biến môi trường.

**spring.config.additional-location** mở rộng tập vị trí mặc định thay vì thay thế, nên là lựa chọn thông dụng khi chỉ muốn file bên ngoài JAR ghi đè một số giá trị mặc định.

**optional:** kiểm soát cách xử lý location bị thiếu; **classpath:**, **file:** và import-relative quyết định cách giải quyết đường dẫn; **configtree:** cho phép nạp một cây file theo cơ chế đặc thù.

Cuối cùng, giá trị mà ứng dụng thực sự sử dụng còn phụ thuộc profile, thứ tự import, nhóm location, các nguồn cấu hình ngoài Config Data và quá trình bind vào kiểu Java. Khi xảy ra lỗi, hãy lần theo đường đi **vị trí tìm kiếm → tài liệu được nạp → tài liệu import → độ ưu tiên PropertySource → bean tiêu thụ** để tìm đúng nguyên nhân.
