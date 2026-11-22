# Suy ra tên automatic module từ tên file JAR

Một JAR không có file module-info.class vẫn có thể được đặt trên module path và sử dụng như một **automatic module**. Khi đó JPMS cần một tên mô-đun để các named module khác có thể khai báo requires tới nó.

Tên automatic module được xác định theo thứ tự ưu tiên: nếu manifest có thuộc tính **Automatic-Module-Name** hợp lệ, Java dùng tên đó; nếu không, Java suy ra tên từ tên file JAR. Vì vậy, tên file artifact có thể ảnh hưởng trực tiếp đến module name mà compiler và JVM nhìn thấy.

Hiểu quy tắc này giúp tránh lỗi module not found, tránh trùng module name và giữ cho module descriptor của ứng dụng ổn định khi thư viện được nâng cấp.

## 1. Automatic module là gì?

Một JAR thông thường có thể chứa các lớp và tài nguyên nhưng không có module descriptor. Khi JAR đó được đặt trên **module path**, Java có thể coi nó là automatic module.

Ví dụ:

~~~text
libs/
└── commons-lang3-3.12.0.jar
~~~

JAR trên không có module-info.class. Khi được đặt trên module path, nó có thể được nhận diện thành automatic module với tên suy ra từ artifact.

Một named module có thể khai báo dependency tới automatic module:

~~~java
module com.example.app {
    requires commons.lang3;
}
~~~

Điều này là một cầu nối quan trọng khi ứng dụng bắt đầu sử dụng JPMS nhưng một số thư viện vẫn chưa phát hành modular JAR.

Vị trí của JAR quyết định cách Java xem nó:

| Vị trí JAR | Cách Java xem JAR |
| --- | --- |
| Trên module path, có module-info.class | Named module với descriptor tường minh. |
| Trên module path, không có module-info.class | Automatic module, tên lấy từ manifest hoặc tên file. |
| Trên classpath | Nội dung thuộc unnamed module; không có tên automatic module để requires. |

Chỉ đưa JAR lên classpath không tạo automatic module. Nếu named module cần khai báo requires tới thư viện, thư viện phải được đưa vào cấu hình module path và có tên mô-đun hợp lệ.

## 2. Thứ tự ưu tiên khi xác định tên

Java xác định module name theo hai trường hợp:

1. **Có Automatic-Module-Name trong manifest:** dùng giá trị của thuộc tính này.
2. **Không có thuộc tính đó:** suy ra tên từ tên file JAR theo quy tắc của automatic module.

Nếu JAR đã có module-info.class, tên mô-đun được khai báo trong descriptor tường minh. Automatic-Module-Name không thay thế tên trong module-info.class.

Manifest nằm trong JAR tại:

~~~text
META-INF/MANIFEST.MF
~~~

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: org.example.payment
~~~

Khi JAR này được đặt trên module path và không có module-info.class, module name là org.example.payment, bất kể tên file artifact là gì.

Khai báo requires phải dùng module name:

~~~java
module com.example.checkout {
    requires org.example.payment;
}
~~~

Nó không dùng groupId, Maven artifactId hoặc nguyên tên file JAR trừ khi các giá trị đó tình cờ giống module name.

## 3. Quy tắc suy ra tên từ tên file JAR

Khi manifest không cung cấp Automatic-Module-Name, Java suy ra tên từ basename của file JAR. Có thể hình dung quá trình theo các bước:

1. Bỏ phần mở rộng .jar.
2. Nhận diện và loại bỏ hậu tố phiên bản ở cuối tên file nếu hậu tố đó có dạng version được quy tắc nhận diện, thường bắt đầu bằng dấu gạch ngang rồi đến chữ số.
3. Thay các chuỗi ký tự không phải chữ hoặc số bằng dấu chấm.
4. Gộp các dấu chấm liên tiếp thành một dấu chấm.
5. Bỏ dấu chấm ở đầu và cuối tên.

Kết quả phải là một tên mô-đun hợp lệ. Không nên tự viết một thuật toán gần giống rồi dùng kết quả đó thay cho module name mà JDK thực sự nhận diện; hãy xác minh bằng công cụ jar.

### 3.1. Ví dụ tên thông thường

| Tên file JAR | Tên automatic module thường được suy ra |
| --- | --- |
| commons-lang3-3.12.0.jar | commons.lang3 |
| jackson-databind-2.17.2.jar | jackson.databind |
| my-library-1.2.0.jar | my.library |
| my_library-1.2.0.jar | my.library |
| my-library.jar | my.library |
| guava-33.0-jre.jar | guava |

Dấu gạch ngang và dấu gạch dưới được chuyển thành dấu chấm. Hậu tố phiên bản nhận diện được sẽ được loại bỏ trước khi chuẩn hóa dấu phân cách.

Tên ví dụ trong bảng minh họa cách suy ra thông thường. Với artifact thực tế, hãy dùng jar --describe-module để xác nhận kết quả do JDK nhận diện.

### 3.2. Hậu tố phiên bản

Một phần phiên bản ở cuối tên file thường không trở thành một phần của module name.

Ví dụ:

~~~text
my-library-1.0.jar
my-library-1.2.3.jar
my-library-2.0-SNAPSHOT.jar
~~~

Các tên trên thường cùng suy ra module name:

~~~text
my.library
~~~

Điều này cho phép nâng cấp từ phiên bản 1.0 lên 1.2.3 mà không phải sửa requires trong module-info.java, miễn là artifact tiếp tục tuân theo quy ước tên và không thay đổi module name tường minh.

Tuy nhiên, không phải mọi chuỗi trông giống phiên bản đều được nhận diện giống nhau. Chẳng hạn, một hậu tố không bắt đầu bằng dạng version được nhận diện có thể bị giữ lại rồi chuẩn hóa thành một phần của tên. Đừng dựa vào cách đặt tên tùy ý nếu module name cần ổn định.

### 3.3. Ký tự phân cách được chuẩn hóa

Các ký tự phân cách như dấu gạch ngang, dấu gạch dưới hoặc dấu chấm lặp lại có thể được chuẩn hóa thành dấu chấm. Ví dụ:

~~~text
my-library.jar
my_library.jar
my..library.jar
~~~

Các tên này có thể cùng dẫn đến:

~~~text
my.library
~~~

Do đó, hai artifact khác nhau về tên file vẫn có thể tạo ra cùng module name. Khi cả hai cùng xuất hiện trên module path, JVM có thể báo trùng mô-đun.

## 4. Automatic-Module-Name trong manifest

Đối với thư viện được phát hành thường xuyên, nên đặt Automatic-Module-Name trong manifest để công bố một tên ổn định.

Ví dụ:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: org.example.customer
~~~

Giả sử artifact được phát hành dưới các tên:

~~~text
customer-1.0.0.jar
customer-1.1.0.jar
customer-2.0.0.jar
~~~

Nếu manifest của từng phiên bản đều khai báo:

~~~text
Automatic-Module-Name: org.example.customer
~~~

thì module name giữ nguyên org.example.customer khi tên file thay đổi.

Mô-đun sử dụng chỉ cần:

~~~java
module com.example.app {
    requires org.example.customer;
}
~~~

Đây là cách tốt hơn việc buộc mọi người dùng phải dựa vào tên artifact để đoán module name. Nó cũng giúp nhà phát hành đổi artifactId, thêm classifier hoặc điều chỉnh quy tắc đặt tên file mà không nhất thiết làm thay đổi module name.

### 4.1. Tạo manifest khi đóng gói JAR

Có thể tạo file manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: org.example.customer

~~~

Khi dùng công cụ jar:

~~~bash
jar --create --file customer.jar --manifest MANIFEST.MF -C classes .
~~~

Với Gradle, có thể đặt thuộc tính manifest cho task đóng gói JAR:

~~~groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Automatic-Module-Name': 'org.example.customer'
        )
    }
}
~~~

Nếu dự án dùng một cấu hình build khác, hãy đặt thuộc tính vào manifest của đúng artifact được phát hành. Kiểm tra JAR đầu ra sau khi build, không chỉ kiểm tra cấu hình nguồn.

## 5. Vì sao tên suy ra có thể gây bất ngờ?

Tên suy ra phụ thuộc vào basename của JAR. Vì vậy, các thay đổi trong cách đóng gói có thể làm module name thay đổi hoặc tạo xung đột.

### 5.1. Đổi tên artifact

Giả sử ban đầu có:

~~~text
customer-client.jar
~~~

Tên suy ra:

~~~text
customer.client
~~~

Sau đó artifact đổi thành:

~~~text
customer-sdk.jar
~~~

Tên suy ra có thể thành:

~~~text
customer.sdk
~~~

Nếu module descriptor vẫn khai báo:

~~~java
requires customer.client;
~~~

compiler hoặc JVM sẽ không tìm thấy module name cũ nếu không còn artifact nào cung cấp tên đó.

Đổi tên file có vẻ chỉ là thao tác phân phối, nhưng với automatic module không có Automatic-Module-Name, nó có thể trở thành thay đổi tương thích ở cấp mô-đun.

### 5.2. Hai phiên bản cùng xuất hiện

Ví dụ:

~~~text
libs/
├── customer-client-1.0.jar
└── customer-client-2.0.jar
~~~

Cả hai có thể suy ra cùng tên customer.client. Module path không phải nơi để đặt đồng thời nhiều phiên bản của cùng một automatic module rồi mong JVM chọn đúng phiên bản theo từng consumer.

Hãy chọn một phiên bản cho module configuration và loại bỏ artifact trùng. Dùng dependency management của Gradle hoặc Maven để giải quyết phiên bản trước khi chạy.

### 5.3. Classifier có thể ảnh hưởng tên

Ví dụ:

~~~text
customer-client-tests-1.0.jar
customer-client-1.0-tests.jar
~~~

Vị trí classifier và version trong tên file có thể làm kết quả suy ra khác nhau. Với tên thứ nhất, phần tests có thể trở thành một thành phần của module name; với tên thứ hai, hậu tố version có thể khiến phần sau bị loại bỏ cùng version.

Không nên giả định mọi artifact phụ như tests, sources, javadoc, all đều có tên mô-đun giống JAR chính. Kiểm tra riêng từng JAR nếu chúng được đặt trên module path.

### 5.4. Tên suy ra không hợp lệ hoặc không như dự kiến

Tên file có thể chứa dấu phân cách ở đầu/cuối, chữ số hoặc chuỗi ký tự bất thường. Sau chuẩn hóa, kết quả có thể không phải một module name hợp lệ hoặc không trùng với tên mà bạn nghĩ.

Nếu JDK không thể tạo automatic module descriptor từ tên file, quá trình tìm hoặc phân giải mô-đun có thể thất bại. Hãy ưu tiên một tên file rõ ràng hoặc khai báo Automatic-Module-Name ổn định trong manifest nếu bạn quản lý thư viện.

## 6. Kiểm tra tên mô-đun mà JDK thực sự sử dụng

Đừng chỉ nhìn tên file. Dùng công cụ JDK:

~~~bash
jar --describe-module --file libs/customer-client-1.0.jar
~~~

Với JAR không có descriptor và không có Automatic-Module-Name, kết quả thường cho biết đó là derived automatic module và hiển thị tên được suy ra.

Với JAR có Automatic-Module-Name, kết quả hiển thị module name được khai báo từ manifest.

Có thể xem các entry trong JAR bằng:

~~~bash
jar --list --file libs/customer-client-1.0.jar
~~~

Lệnh trên liệt kê entry trong JAR, bao gồm đường dẫn META-INF/MANIFEST.MF. Để đọc nội dung manifest, có thể giải nén riêng entry đó vào thư mục tạm hoặc dùng công cụ kiểm tra ZIP phù hợp; tránh ghi đè file trong workspace hiện tại.

Khi cần xem các mô-đun có thể quan sát trong môi trường chạy:

~~~bash
java --module-path libs --list-modules
~~~

Và để quan sát quá trình phân giải khi khởi chạy ứng dụng:

~~~bash
java --show-module-resolution --module-path libs:mods \
    -m com.example.app/com.example.app.Main
~~~

Trên Windows, dấu phân cách các phần tử module path là dấu chấm phẩy. Luôn chạy lệnh trong đúng JDK và đúng cấu hình mà ứng dụng sử dụng khi triển khai.

## 7. Dùng module name trong module-info.java

Giả sử JAR commons-lang3-3.12.0.jar được nhận diện với tên commons.lang3. Named module có thể khai báo:

~~~java
module com.example.text {
    requires commons.lang3;
}
~~~

Tên sau requires phải là module name, không phải tên file:

~~~java
// Không dùng tên file:
requires commons-lang3-3.12.0;

// Dùng tên mô-đun đã xác minh:
requires commons.lang3;
~~~

Ví dụ trên chỉ minh họa cú pháp; tên thực tế phải được xác nhận bằng jar --describe-module trên đúng artifact đang sử dụng.

Một automatic module thường đọc được các mô-đun khác trong cấu hình và export toàn bộ package của nó. Vì vậy, nó giúp thư viện cũ dễ được sử dụng từ named module, nhưng không tạo ranh giới API chặt như một named module có module-info.java được thiết kế rõ ràng.

## 8. Automatic module khác named module tường minh thế nào?

| Đặc điểm | Automatic module | Named module có module-info.java |
| --- | --- | --- |
| Nguồn tên | Manifest hoặc tên file JAR | Chỉ thị module trong module-info.java |
| Dependency | Có khả năng đọc rộng các mô-đun khác | Khai báo bằng requires |
| Package API | Export toàn bộ package | Chỉ export package được chọn |
| Reflection | Package được mở rộng cho deep reflection | Chỉ opens package cần thiết |
| Mục tiêu thường gặp | Cầu nối cho thư viện cũ | Thiết kế mô-đun có ranh giới rõ ràng |

Automatic module hữu ích trong giai đoạn chuyển đổi, nhưng không nên xem nó là cấu hình đóng gói cuối cùng cho mọi thư viện. Khi có thể, nhà phát hành nên bổ sung module descriptor thực sự để kiểm soát dependency, package API và reflection.

## 9. Lỗi thường gặp khi suy ra tên

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| module not found | requires dùng tên khác với tên JDK suy ra | Chạy jar --describe-module và sửa requires. |
| Duplicate module hoặc lỗi module trùng | Hai JAR cùng suy ra một module name | Loại bỏ artifact/phiên bản trùng khỏi module path. |
| Đổi phiên bản làm build lỗi | Tên artifact thay đổi khiến module name thay đổi | Dùng Automatic-Module-Name ổn định hoặc giữ quy ước tên. |
| JAR chạy trên classpath nhưng không dùng được requires | Trên classpath nó thuộc unnamed module | Đưa JAR lên module path và xác minh automatic module name. |
| JAR classifier tạo module name bất ngờ | Classifier và version nằm ở vị trí khác nhau | Kiểm tra riêng từng JAR bằng công cụ jar. |
| Tên suy ra không hợp lệ | Basename tạo ra module name không hợp lệ | Đổi quy ước tên artifact hoặc đặt Automatic-Module-Name. |

## 10. Quy trình chẩn đoán và xử lý

Khi một named module báo không tìm thấy dependency hoặc tên mô-đun thay đổi sau khi nâng cấp thư viện:

1. Lấy đúng file JAR mà build hoặc runtime đang sử dụng.
2. Chạy jar --describe-module --file path/to/library.jar.
3. Xác định JAR có module-info.class, Automatic-Module-Name hay phải suy ra tên từ file.
4. So sánh module name kết quả với tên sau requires trong module-info.java.
5. Kiểm tra xem module path có chứa nhiều phiên bản hoặc artifact classifier cùng tên mô-đun không.
6. Nếu bạn quản lý thư viện, cân nhắc công bố Automatic-Module-Name ổn định hoặc chuyển sang module descriptor tường minh.
7. Chạy lại compile và runtime bằng đúng cấu hình triển khai.

Nếu module name chỉ thay đổi vì tên file, có thể sửa requires để khớp tên mới. Nhưng với thư viện được phát hành công khai, tốt hơn là ổn định tên bằng manifest hoặc descriptor để người dùng không phải thay đổi mã nguồn theo mỗi lần đổi artifact name.

## 11. Nguyên tắc đặt tên ổn định

- Ưu tiên module name có ý nghĩa và ổn định, thường theo quy ước tên miền đảo ngược.
- Nếu bạn phát hành thư viện chưa modular hóa nhưng muốn hỗ trợ module path, khai báo Automatic-Module-Name trong manifest.
- Không đưa số phiên bản vào Automatic-Module-Name.
- Không phụ thuộc vào classifier hoặc tên file tạm thời để xác định module name.
- Kiểm tra module name của từng JAR được đưa lên module path.
- Tránh đưa hai phiên bản cùng module name vào một module configuration.
- Khi có thể, chuyển từ automatic module sang named module có descriptor tường minh để kiểm soát requires, exports và opens.

## 12. Tự kiểm tra

**Tình huống 1:** JAR tên commons-lang3-3.12.0.jar không có module-info.class và manifest không có Automatic-Module-Name. Cần làm gì để biết module name?

Trả lời: dùng jar --describe-module --file commons-lang3-3.12.0.jar để xem tên automatic module mà JDK thực sự suy ra. Không tự đoán tên chỉ từ artifactId.

**Tình huống 2:** Bạn đổi tên file từ customer-client.jar thành customer-sdk.jar, sau đó requires customer.client báo module not found. Vì sao?

Trả lời: nếu không có Automatic-Module-Name, module name được suy ra từ tên file. Tên suy ra có thể đã thay đổi thành customer.sdk. Khai báo Automatic-Module-Name ổn định giúp tránh phụ thuộc vào tên file.

**Tình huống 3:** Hai phiên bản library-1.0.jar và library-2.0.jar cùng nằm trên module path. Vì sao có thể xảy ra lỗi?

Trả lời: cả hai có thể suy ra cùng module name library. Module configuration không thể coi chúng là hai mô-đun độc lập chỉ vì tên file khác nhau. Hãy chọn một phiên bản.

**Tình huống 4:** Thư viện chạy được khi nằm trên classpath nhưng named module không thể requires tới nó. Vì sao?

Trả lời: trên classpath, JAR thuộc unnamed module và không có module name để khai báo requires. Đưa JAR lên module path để Java nhận diện automatic module hoặc bổ sung module descriptor phù hợp.

**Tình huống 5:** Một JAR có Automatic-Module-Name và tên file bị đổi. Module name có nhất thiết đổi không?

Trả lời: không. Nếu JAR vẫn không có module-info.class và manifest giữ nguyên Automatic-Module-Name hợp lệ, tên automatic module tiếp tục lấy từ manifest. Hãy xác minh bằng công cụ jar sau khi đóng gói.
