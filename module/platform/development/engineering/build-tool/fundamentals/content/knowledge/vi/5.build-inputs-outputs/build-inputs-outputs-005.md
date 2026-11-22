# Quan hệ giữa đầu vào, đầu ra và việc quyết định chạy lại một bước

Một công cụ build không nhất thiết phải thực hiện lại mọi bước mỗi lần người phát triển yêu cầu build. Nếu mã nguồn, cấu hình và các dữ liệu liên quan vẫn giữ nguyên, kết quả của một bước có thể vẫn còn hợp lệ. Công cụ build có thể bỏ qua bước đó và tiếp tục dùng đầu ra đã tạo trước đây. Khi đầu vào thay đổi, đầu ra bị thiếu hoặc trạng thái trước đó không còn đáng tin cậy, bước tương ứng cần được chạy lại.

Để hiểu cách quyết định này hoạt động, cần nhìn mỗi bước build như một phép biến đổi: nó đọc một tập đầu vào, thực hiện công việc và tạo ra một tập đầu ra. Mối quan hệ giữa hai tập này, cùng với quan hệ phụ thuộc giữa các bước, là cơ sở để công cụ build xác định phần công việc nào còn cần thực hiện.

## 1. Một bước build là phép biến đổi từ đầu vào thành đầu ra

Một bước build (task, goal hoặc action tùy công cụ) thực hiện một công việc cụ thể. Ví dụ:

- Biên dịch mã nguồn Java thành bytecode.
- Sao chép và xử lý tài nguyên vào thư mục đầu ra.
- Sinh mã Java từ tệp mô tả hoặc schema.
- Đóng gói các lớp và tài nguyên thành tệp JAR.
- Chạy kiểm thử và tạo báo cáo.

Có thể mô tả một bước bằng mô hình:

    Đầu vào  --->  Bước xử lý  --->  Đầu ra

Với bước biên dịch Java:

    Product.java, Main.java, thư viện, tùy chọn compiler
                       |
                       v
                  javac / compile
                       |
                       v
             Product.class, Main.class

Đầu vào là những thông tin có ảnh hưởng tới kết quả. Đầu ra là những tệp hoặc giá trị mà bước tạo ra. Nếu một đầu vào thay đổi theo cách có thể ảnh hưởng kết quả, đầu ra cũ có thể không còn đúng và bước cần chạy lại.

Ví dụ, khi chỉ sửa README mà không có bước build nào đọc README, việc biên dịch Java không cần chạy lại. Nhưng khi sửa Product.java, bước biên dịch có sử dụng tệp đó phải được xem xét lại.

## 2. Đầu vào gồm những gì?

Đầu vào không chỉ là tệp mã nguồn. Tất cả dữ liệu có thể làm thay đổi kết quả của bước đều có thể là đầu vào.

### Tệp nguồn và tài nguyên

Với bước biên dịch Java, đầu vào thường gồm:

- Tệp Java trong thư mục nguồn.
- Tệp tài nguyên được xử lý hoặc đóng gói.
- Tệp sinh mã, schema, template hoặc dữ liệu dùng để tạo mã nguồn.
- Tệp cấu hình mà bước đọc trong quá trình thực hiện.

Nếu một bước xử lý nhiều tệp trong một thư mục, tập đầu vào cần phản ánh cả việc thêm, xóa và đổi tên tệp. Chỉ theo dõi một tệp đại diện có thể khiến thay đổi ở các tệp còn lại không được phát hiện.

### Cấu hình và tham số

Một bước có thể đọc cấu hình như:

- Phiên bản Java hoặc mức ngôn ngữ nguồn.
- Tùy chọn compiler.
- Encoding của mã nguồn.
- Tên package gốc hoặc thư mục đích.
- Cờ bật/tắt một tính năng.
- Tham số truyền vào task.

Giả sử mã nguồn không đổi nhưng mức ngôn ngữ chuyển từ Java 17 sang Java 21. Kết quả biên dịch có thể thay đổi vì compiler và quy tắc ngôn ngữ đã thay đổi. Vì vậy, cấu hình có ảnh hưởng đến kết quả cũng phải được xem là đầu vào.

### Công cụ và môi trường thực thi

Phiên bản JDK, compiler, plugin hoặc chương trình bên ngoài có thể ảnh hưởng kết quả. Tùy công cụ build, một phần thông tin này được theo dõi tự động; phần khác cần được khai báo hoặc cố định trong cấu hình dự án.

Các giá trị môi trường như biến môi trường, locale hoặc tham số hệ thống cũng có thể ảnh hưởng kết quả. Nếu bước đọc chúng nhưng công cụ build không biết rằng chúng là đầu vào, công cụ có thể kết luận nhầm rằng kết quả cũ vẫn dùng được.

### Đầu ra của bước khác

Đầu ra của một bước có thể trở thành đầu vào của bước tiếp theo. Ví dụ:

- Tệp .java là đầu vào của bước biên dịch.
- Tệp .class là đầu vào của bước đóng gói JAR.
- Tệp JAR là đầu vào của bước kiểm thử tích hợp hoặc bước phân phối.

Khi đầu ra của bước trước thay đổi, các bước phía sau có sử dụng đầu ra đó cũng có thể cần chạy lại.

## 3. Đầu ra là gì và vì sao phải khai báo?

Đầu ra là kết quả mà bước tạo ra và các bước khác có thể cần sử dụng. Đầu ra thường là tệp hoặc thư mục, chẳng hạn:

- Các tệp .class trong thư mục build/classes.
- Mã nguồn Java được sinh trong build/generated.
- Tệp JAR trong build/libs.
- Tệp đã xử lý trong build/resources.
- Báo cáo kiểm thử hoặc kết quả phân tích.

Khai báo đầu ra giúp công cụ build biết kết quả nào thuộc về bước, kiểm tra xem kết quả còn tồn tại hay đã bị thay đổi, và xác định dữ liệu nào có thể được tái sử dụng. Nếu bước tạo tệp nhưng không khai báo đầu ra, công cụ có thể không đủ thông tin để kiểm tra trạng thái hoặc lưu và khôi phục kết quả qua build cache.

Đầu ra cần được đặt ở vị trí phù hợp, thường là thư mục build riêng. Không nên ghi tệp sinh ra đè lên mã nguồn gốc hoặc trộn đầu ra build với tệp do người phát triển duy trì. Việc tách hai loại tệp giúp dọn build, phát hiện tệp cũ và tái tạo kết quả dễ dàng hơn.

## 4. Công cụ build quyết định chạy lại như thế nào?

Một công cụ build có thể dùng thuật toán và mức theo dõi khác nhau, nhưng nguyên tắc chung là so sánh trạng thái hiện tại với trạng thái đã ghi nhận từ lần chạy trước.

Một bước thường cần chạy lại khi có một trong các tình huống sau:

1. **Chưa từng chạy hoặc không có trạng thái trước đó:** công cụ chưa có cơ sở để xác nhận đầu ra hiện tại hợp lệ.
2. **Thiếu đầu ra:** tệp hoặc thư mục mà bước cần tạo đã bị xóa hoặc chưa được tạo.
3. **Đầu vào thay đổi:** tệp nguồn, tài nguyên, cấu hình hoặc tham số có ảnh hưởng đến kết quả đã thay đổi.
4. **Đầu ra bị thay đổi hoặc không còn khớp trạng thái đã ghi nhận:** một người hoặc công cụ khác đã sửa, thay thế hay làm hỏng kết quả.
5. **Bước phụ thuộc tạo ra kết quả mới:** bước hiện tại cần dùng đầu ra mới của một bước trước đó.
6. **Môi trường hoặc cách thực hiện thay đổi:** phiên bản công cụ, implementation của task hoặc một thuộc tính được theo dõi đã thay đổi.

Nếu đầu vào và cấu hình liên quan không đổi, đầu ra vẫn tồn tại và trạng thái của nó khớp với trạng thái đã ghi nhận, công cụ có thể đánh dấu bước là up-to-date và bỏ qua việc thực thi.

| Trạng thái | Hành động thường thấy |
| --- | --- |
| Chưa có kết quả trước đó | Chạy bước |
| Đầu ra bị thiếu | Chạy lại bước để tạo đầu ra |
| Đầu vào liên quan thay đổi | Chạy lại bước |
| Đầu ra bị sửa hoặc mất tính hợp lệ | Chạy lại bước |
| Đầu vào không đổi, đầu ra còn hợp lệ | Bỏ qua bước vì đã up-to-date |
| Có kết quả tương ứng trong build cache | Có thể khôi phục đầu ra từ cache thay vì thực thi lại |

Không phải mọi công cụ đều dùng cùng một thuật ngữ hoặc kiểm tra cùng một tập thuộc tính. Một số công cụ dựa nhiều vào thời gian sửa đổi tệp; một số công cụ lưu snapshot nội dung và thông tin task. Cần hiểu hành vi cụ thể của công cụ đang dùng khi chẩn đoán build.

## 5. Quan hệ phụ thuộc giữa các bước

Các bước build thường tạo thành một đồ thị phụ thuộc. Một bước chỉ có thể chạy khi những bước cần thiết trước nó đã hoàn tất và đầu vào của nó đã sẵn sàng.

Ví dụ với ứng dụng Java:

    Mã nguồn Java
          |
          v
       Biên dịch
          |
          v
      Tệp .class
          |
          v
      Đóng gói JAR
          |
          v
        Tệp JAR
          |
          v
       Kiểm thử

Giả sử chỉ sửa một tệp Java. Bước biên dịch có liên quan cần chạy lại. Vì bytecode đầu ra có thể thay đổi, bước đóng gói JAR cũng cần cập nhật gói. Bước kiểm thử sử dụng JAR mới có thể phải chạy lại.

Ngược lại, nếu chỉ sửa một tài liệu không nằm trong đồ thị phụ thuộc, các bước biên dịch và đóng gói không cần chạy lại. Đây là lợi ích của việc mô tả đúng quan hệ đầu vào, đầu ra và phụ thuộc.

### Phụ thuộc về thứ tự và phụ thuộc về dữ liệu

Hai bước có thể cần chạy theo thứ tự ngay cả khi bước sau không đọc tệp đầu ra của bước trước. Đây là phụ thuộc về thứ tự. Ví dụ, bước kiểm tra môi trường phải hoàn tất trước khi chạy một bước triển khai.

Phụ thuộc về dữ liệu xuất hiện khi bước sau thực sự đọc đầu ra do bước trước tạo ra. Đây là mối quan hệ quan trọng đối với việc phát hiện thay đổi: khi dữ liệu được tạo ra thay đổi, bước tiêu thụ dữ liệu đó có thể cần chạy lại.

Khai báo một phụ thuộc thứ tự không nhất thiết thay thế việc khai báo đầu vào. Nếu bước sau đọc một tệp cụ thể, cần mô tả tệp đó như đầu vào để công cụ có thể kiểm tra trạng thái chính xác.

## 6. Ví dụ: biên dịch Java và đóng gói JAR

Giả sử dự án có các tệp:

    src/main/java/
      com/example/Main.java
      com/example/Product.java
    src/main/resources/
      application.properties

Quy trình build có thể gồm ba bước:

| Bước | Đầu vào | Đầu ra |
| --- | --- | --- |
| Biên dịch | Tệp .java, classpath, tùy chọn compiler | Tệp .class |
| Xử lý tài nguyên | Tệp trong src/main/resources, quy tắc xử lý | Tài nguyên trong thư mục đầu ra |
| Đóng gói | Tệp .class và tài nguyên đã xử lý | Tệp JAR |

Nếu chỉ sửa application.properties, bước xử lý tài nguyên cần chạy lại và JAR cần được cập nhật. Việc biên dịch Java có thể được bỏ qua nếu không có đầu vào biên dịch nào thay đổi.

Nếu sửa Product.java, bước biên dịch cần chạy lại. Khi bytecode thay đổi, bước đóng gói cần tạo lại JAR. Nếu kiểm thử sử dụng JAR đó, kiểm thử cũng có thể phải chạy lại.

Nếu xóa JAR trong build/libs nhưng không sửa mã nguồn, bước biên dịch vẫn có thể up-to-date vì các tệp .class của nó còn hợp lệ. Bước đóng gói phải chạy lại vì đầu ra JAR bị thiếu.

Ví dụ này cho thấy công cụ không cần chạy lại toàn bộ quy trình chỉ vì một đầu ra bị thiếu. Nó có thể thực hiện lại đúng bước chịu trách nhiệm tạo đầu ra đó và những bước phía sau thực sự phụ thuộc vào kết quả mới.

## 7. Khai báo đầu vào và đầu ra trong Gradle

Gradle dùng mô hình task và có thể kiểm tra trạng thái đầu vào, đầu ra để quyết định task có cần thực thi hay không. Khi viết custom task, cần khai báo những dữ liệu mà task đọc và những kết quả mà task tạo ra.

Ví dụ sau tạo một tệp chứa phiên bản đọc từ version.txt:

    tasks.register('generateVersion') {
        inputs.file('version.txt')
        outputs.file(layout.buildDirectory.file('generated/version.txt'))

        doLast {
            def outputFile = layout.buildDirectory.file('generated/version.txt').get().asFile
            outputFile.parentFile.mkdirs()
            outputFile.text = file('version.txt').text.trim()
        }
    }

Trong ví dụ:

- **inputs.file('version.txt')** khai báo tệp mà task đọc.
- **outputs.file(...)** khai báo tệp mà task tạo.
- Tệp đầu ra nằm trong thư mục build để có thể tạo lại.
- Phần **doLast** thực hiện công việc ghi nội dung.

Khi task đã chạy thành công, nếu version.txt không đổi và tệp đầu ra vẫn tồn tại với trạng thái được Gradle ghi nhận, lần chạy sau task có thể được đánh dấu **UP-TO-DATE**. Nếu version.txt thay đổi hoặc tệp đầu ra bị xóa, task cần thực thi lại.

Nếu task còn đọc một thuộc tính cấu hình, chẳng hạn chế độ phát hành, cần khai báo thuộc tính đó như một đầu vào:

    tasks.register('generateReleaseInfo') {
        inputs.file('version.txt')
        inputs.property('releaseMode', providers.gradleProperty('releaseMode').orElse('false'))
        outputs.file(layout.buildDirectory.file('generated/release-info.txt'))

        doLast {
            def releaseMode = providers.gradleProperty('releaseMode').getOrElse('false')
            def outputFile = layout.buildDirectory.file('generated/release-info.txt').get().asFile
            outputFile.parentFile.mkdirs()
            outputFile.text = file('version.txt').text.trim() + '\nrelease=' + releaseMode
        }
    }

Khi giá trị releaseMode thay đổi, kết quả có thể thay đổi nên task cần được xem là không còn up-to-date. Ví dụ minh họa này tập trung vào cách khai báo; trong dự án thực tế nên dùng cùng một provider đã chuẩn hóa cho cả khai báo đầu vào và phần thực thi để tránh đọc các giá trị không nhất quán.

Với task có kiểu chuyên biệt như biên dịch Java, Gradle plugin thường đã khai báo đầu vào và đầu ra phù hợp. Người phát triển nên tận dụng task có sẵn thay vì tự tạo task biên dịch mới nếu không có nhu cầu đặc biệt.

## 8. Vì sao khai báo thiếu đầu vào gây lỗi?

Giả sử một task đọc cả version.txt và biến môi trường RELEASE_CHANNEL, nhưng chỉ khai báo version.txt là đầu vào.

Lần đầu task chạy với RELEASE_CHANNEL là beta và tạo ra tệp đầu ra chứa beta. Sau đó biến môi trường đổi thành production, trong khi version.txt không đổi. Nếu Gradle không biết RELEASE_CHANNEL ảnh hưởng kết quả, task có thể bị đánh dấu up-to-date và không chạy lại. Tệp đầu ra vẫn chứa beta dù cấu hình hiện tại là production.

Đây là một lỗi mô tả phụ thuộc: công việc thực tế đọc nhiều dữ liệu hơn tập đầu vào mà công cụ build biết.

Những trường hợp thường bị bỏ sót:

- Biến môi trường hoặc system property.
- Tệp cấu hình đọc gián tiếp.
- Tệp schema hoặc template được dùng để sinh mã.
- Phiên bản chương trình ngoài được gọi từ task.
- Tham số truyền vào script.
- Danh sách tệp được quét động.

Khi đầu vào không được khai báo đầy đủ, công cụ có thể bỏ qua một bước đáng lẽ cần chạy lại. Ngược lại, khai báo đầu vào quá rộng hoặc không ổn định có thể khiến task chạy lại thường xuyên dù kết quả không thay đổi.

## 9. Vì sao khai báo thiếu đầu ra gây khó khăn?

Nếu task tạo một tệp nhưng không khai báo tệp đó là đầu ra, công cụ build có thể không biết tệp thuộc về task nào. Điều này gây ra một số vấn đề:

- Không thể kiểm tra đáng tin cậy việc đầu ra bị xóa hoặc bị thay đổi.
- Khó xác định bước nào phải chạy lại để tái tạo tệp.
- Khó tái sử dụng đầu ra qua build cache.
- Các bước phía sau có thể không được nối với bước tạo dữ liệu một cách rõ ràng.

Hãy khai báo toàn bộ đầu ra mà task sở hữu, kể cả khi task tạo nhiều tệp. Nếu task tạo một thư mục chứa mã nguồn sinh ra, khai báo đúng thư mục đó hoặc tập tệp phù hợp. Không khai báo một thư mục quá rộng bao gồm cả tệp do người phát triển chỉnh sửa thủ công, vì công cụ có thể coi chúng là đầu ra có thể xóa hoặc thay thế.

## 10. Up-to-date và build cache khác nhau thế nào?

Hai cơ chế này đều giúp tránh thực hiện công việc không cần thiết, nhưng chúng không giống nhau.

### Up-to-date check

Up-to-date check xác định một task trong workspace hiện tại có cần chạy lại hay không. Nếu trạng thái đầu vào và đầu ra khớp với lần chạy trước, task được bỏ qua. Trong Gradle, đầu ra thường hiển thị trạng thái **UP-TO-DATE**.

Ví dụ: bạn vừa build dự án thành công, không sửa tệp nào và chạy build lần nữa. Những task có đầu vào và đầu ra không đổi có thể được bỏ qua.

### Build cache

Build cache cho phép tái sử dụng đầu ra của một task từ một lần build trước đó hoặc từ một máy khác, nếu task được cấu hình để cache và khóa đầu vào phù hợp. Nếu task cần thực hiện nhưng có kết quả tương ứng trong cache, Gradle có thể khôi phục đầu ra mà không thực thi lại phần công việc của task. Trạng thái thường hiển thị **FROM-CACHE**.

Ví dụ: một thành viên mới clone dự án và build lần đầu. Workspace của họ chưa có đầu ra cục bộ, nhưng build cache có thể chứa kết quả biên dịch tương ứng. Nếu task cacheable và các đầu vào khớp, đầu ra có thể được lấy từ cache.

| Cơ chế | Nguồn đầu ra | Khi nào hữu ích |
| --- | --- | --- |
| Up-to-date | Đầu ra đã có trong workspace hiện tại | Build lặp lại khi không có thay đổi liên quan |
| Build cache | Đầu ra được lưu trong cache cục bộ hoặc từ xa | Workspace khác hoặc lần build khác có cùng đầu vào |

Một task được đánh dấu up-to-date vì kết quả hiện tại trong workspace còn hợp lệ. Một task được lấy from-cache vì đầu ra phù hợp được khôi phục từ cache. Cả hai đều có thể tránh thực thi task, nhưng lý do và nguồn dữ liệu khác nhau.

## 11. Khác biệt giữa kiểm tra theo thời gian và kiểm tra nội dung

Một số công cụ build đơn giản, chẳng hạn quy trình kiểu Make truyền thống, thường dùng thời gian sửa đổi của tệp để xác định đầu vào mới hơn đầu ra hay không. Cách này nhanh và dễ hiểu, nhưng phụ thuộc vào timestamp và cách cập nhật tệp.

Các hệ thống build hiện đại có thể lưu snapshot đầu vào và đầu ra, bao gồm thông tin về nội dung, đường dẫn, loại tệp hoặc thuộc tính khác. Gradle sử dụng snapshot và lịch sử task để thực hiện up-to-date check. Việc kiểm tra cụ thể còn phụ thuộc loại task và phiên bản công cụ.

Không nên giả định mọi công cụ đều phát hiện thay đổi theo cùng một cách. Khi build không chạy lại như mong đợi, hãy xem tài liệu và log của công cụ để biết nó đang theo dõi những thuộc tính nào.

## 12. Tác động của bước clean

Lệnh clean thường xóa các đầu ra build đã tạo trong workspace. Ví dụ, với Gradle:

    ./gradlew clean
    ./gradlew build

Trên Windows có thể dùng:

    gradlew.bat clean
    gradlew.bat build

Sau khi clean, các đầu ra cục bộ bị xóa. Những task chịu trách nhiệm tạo các đầu ra đó phải chạy lại khi build tiếp theo. Tuy nhiên, nếu build cache được bật và task có thể cache, một số đầu ra vẫn có thể được khôi phục từ cache.

Clean hữu ích khi muốn loại bỏ trạng thái build cục bộ cũ hoặc kiểm tra khả năng tạo lại sản phẩm từ đầu. Nhưng không cần chạy clean trước mọi lần build: làm vậy sẽ loại bỏ cơ hội tận dụng đầu ra hợp lệ đang có trong workspace.

## 13. Cách chẩn đoán khi một bước chạy lại hoặc bị bỏ qua ngoài dự kiến

Khi một task chạy lại dù bạn nghĩ đầu vào không đổi, hãy kiểm tra theo trình tự:

1. Xác định chính xác task nào chạy lại.
2. Xem task đã khai báo những tệp, thuộc tính và tham số nào làm đầu vào.
3. Kiểm tra có tệp đầu vào nào được thêm, xóa, đổi tên hoặc thay đổi nội dung không.
4. Kiểm tra đầu ra có bị xóa, sửa thủ công hoặc tạo ở sai vị trí không.
5. Kiểm tra phiên bản JDK, plugin, compiler hoặc cấu hình build có thay đổi không.
6. Xem log chi tiết để tìm lý do task không còn up-to-date.

Với Gradle, có thể yêu cầu log chi tiết hơn:

    ./gradlew compileJava --info

Trên Windows:

    gradlew.bat compileJava --info

Nếu cần buộc task chạy lại để so sánh kết quả, Gradle hỗ trợ:

    ./gradlew compileJava --rerun-tasks

Tùy chọn này buộc task được yêu cầu chạy lại, hữu ích cho việc chẩn đoán. Nó không sửa được khai báo đầu vào hoặc đầu ra bị thiếu. Sau khi thử, cần quay lại sửa nguyên nhân trong cấu hình task nếu có.

Khi một task bị bỏ qua dù kết quả cũ không còn đúng, hãy tìm đầu vào mà task thực sự đọc nhưng chưa khai báo. Kiểm tra cả tham số, biến môi trường, tệp cấu hình và chương trình bên ngoài. Sau khi bổ sung khai báo, thay đổi ở đầu vào đó mới có thể được công cụ theo dõi đúng.

## 14. Nguyên tắc để build có thể dự đoán

Một task dễ được quản lý chính xác khi tuân thủ các nguyên tắc sau:

- **Khai báo đủ đầu vào:** mọi dữ liệu ảnh hưởng kết quả đều phải được công cụ nhận biết.
- **Khai báo đủ đầu ra:** công cụ biết task tạo ra tệp hoặc thư mục nào.
- **Giữ đầu ra trong thư mục build:** tệp sinh ra không trộn với mã nguồn được chỉnh sửa thủ công.
- **Tạo kết quả ổn định:** cùng đầu vào và cùng cấu hình nên tạo ra kết quả tương đương.
- **Tránh phụ thuộc ngầm:** không dựa vào tệp hoặc biến môi trường không được khai báo.
- **Mô tả phụ thuộc rõ ràng:** bước tiêu thụ dữ liệu cần phụ thuộc vào bước tạo dữ liệu đó.
- **Không dùng đầu ra làm nơi lưu dữ liệu thủ công:** công cụ có thể xóa hoặc tạo lại đầu ra khi cần.

Tính ổn định đặc biệt quan trọng đối với build cache. Nếu một task tạo kết quả khác nhau dù các đầu vào được khai báo giống nhau, việc tái sử dụng đầu ra có thể tạo ra kết quả sai. Ví dụ, task tự đọc thời gian hiện tại hoặc dữ liệu mạng nhưng không khai báo các giá trị đó là đầu vào không thể được coi là phép biến đổi ổn định chỉ dựa trên các tệp đã khai báo.

## 15. Ví dụ tổng hợp về quyết định chạy lại

Giả sử quy trình có ba task:

    processResources:
        input: src/main/resources/**
        output: build/resources/**

    compileJava:
        input: src/main/java/**, classpath, compiler options
        output: build/classes/**

    jar:
        input: build/resources/**, build/classes/**
        output: build/libs/app.jar

Kết quả có thể diễn ra như sau:

| Thay đổi | processResources | compileJava | jar |
| --- | --- | --- | --- |
| Không có thay đổi | Có thể bỏ qua | Có thể bỏ qua | Có thể bỏ qua |
| Sửa một tệp resource | Chạy lại | Có thể bỏ qua | Chạy lại |
| Sửa một tệp Java | Có thể bỏ qua | Chạy lại | Chạy lại |
| Xóa app.jar | Có thể bỏ qua | Có thể bỏ qua | Chạy lại |
| Thay đổi compiler options | Có thể bỏ qua | Chạy lại | Chạy lại nếu bytecode mới làm thay đổi đầu vào đóng gói |

Bảng giả định các task khai báo đúng đầu vào và đầu ra, không có phụ thuộc bổ sung và đầu ra khác vẫn hợp lệ. Hành vi thực tế có thể thay đổi theo cách plugin và công cụ build cấu hình task.

Điều cần ghi nhớ là công cụ build quyết định chạy lại dựa trên quan hệ đã khai báo giữa đầu vào, đầu ra và các bước phụ thuộc. Khai báo càng đầy đủ và chính xác, công cụ càng có thể bỏ qua phần việc không cần thiết mà vẫn giữ kết quả build đúng. Khai báo thiếu có thể khiến kết quả cũ được dùng sai; khai báo quá rộng có thể làm mất lợi ích của build tăng dần.
