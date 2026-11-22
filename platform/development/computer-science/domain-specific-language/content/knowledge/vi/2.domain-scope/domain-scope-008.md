# Biến thể và điểm mở rộng

DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền) được thiết kế để diễn đạt công việc trong một miền vấn đề. Tuy nhiên, DSL không có một hình thức duy nhất. Có DSL dùng cú pháp văn bản riêng, có DSL được nhúng trong ngôn ngữ lập trình; có DSL mô tả kết quả mong muốn, có DSL mô tả từng bước thực hiện. Một số DSL có phạm vi rất hẹp, trong khi số khác phục vụ một hoạt động chung xuất hiện ở nhiều lĩnh vực.

Khi tìm hiểu phạm vi miền, cần xem DSL theo hai khía cạnh liên quan: **biến thể** cho biết DSL được tổ chức và sử dụng theo cách nào; **điểm mở rộng** cho biết người dùng có thể bổ sung khái niệm, quy tắc hoặc khả năng mới vào DSL ở đâu và bằng cách nào.

## 1. Các chiều phân loại DSL

Các cách phân loại dưới đây mô tả những chiều thiết kế khác nhau. Chúng không phải các nhóm loại trừ lẫn nhau. Một DSL có thể đồng thời là DSL bên ngoài, dạng văn bản, khai báo và có cơ chế mở rộng bằng plugin.

### 1.1. Theo phạm vi miền: DSL dọc và DSL ngang

**DSL dọc** (*vertical DSL*) tập trung vào một ngành hoặc một miền nghiệp vụ tương đối cụ thể. Từ vựng và quy tắc của nó phản ánh kiến thức chuyên môn trong miền đó.

Ví dụ:

- Ngôn ngữ mô tả hợp đồng bảo hiểm có thể có các khái niệm về hợp đồng, quyền lợi, phí và điều kiện chi trả.
- Ngôn ngữ mô hình hóa quy trình sản xuất có thể mô tả dây chuyền, công đoạn, thiết bị và tiêu chuẩn chất lượng.
- Ngôn ngữ mô tả giao dịch tài chính có thể biểu diễn lệnh, tài khoản, hạn mức và quy tắc quyết toán.

DSL dọc có thể giúp chuyên gia nghiệp vụ diễn đạt quy tắc gần với cách họ hiểu công việc. Đổi lại, nó cần mô hình miền đủ chính xác và thường có phạm vi áp dụng hẹp hơn.

**DSL ngang** (*horizontal DSL*) tập trung vào một loại hoạt động có thể xuất hiện trong nhiều ngành hoặc nhiều dự án. Ví dụ:

- SQL tập trung vào truy vấn và thao tác dữ liệu quan hệ, được dùng trong nhiều lĩnh vực.
- Regex mô tả mẫu văn bản và được sử dụng trong nhiều loại ứng dụng.
- Ngôn ngữ cấu hình build mô tả mục tiêu, phụ thuộc và tác vụ xây dựng phần mềm.

DSL ngang thường tái sử dụng được ở nhiều nơi vì nó tập trung vào một công việc chung. Tuy vậy, người dùng vẫn cần kết nối các khái niệm tổng quát của DSL với mô hình cụ thể của hệ thống.

Ranh giới dọc và ngang phụ thuộc vào cách xác định miền. Một DSL truy vấn có thể là ngang nếu xét trên nhiều ngành, nhưng lại là chuyên biệt nếu xét trong phạm vi một hệ quản trị dữ liệu cụ thể.

### 1.2. Theo cách triển khai: DSL bên ngoài và DSL nhúng

**DSL bên ngoài** (*external DSL*) có cú pháp riêng, thường được lưu trong tệp hoặc nhập vào một công cụ chuyên biệt. Công cụ đó phân tích cú pháp, kiểm tra quy tắc rồi diễn giải hoặc chuyển đổi nội dung DSL.

Ví dụ, SQL có cú pháp truy vấn riêng và được hệ quản trị cơ sở dữ liệu phân tích. CSS có cú pháp khai báo quy tắc hiển thị và được trình duyệt xử lý. Người viết không cần biểu diễn các câu lệnh này bằng cú pháp của Java hay Python.

**DSL nhúng** (*embedded DSL* hoặc *internal DSL*) được xây dựng bên trong một ngôn ngữ chủ (*host language*). DSL tận dụng cú pháp, hàm, đối tượng, toán tử hoặc hệ kiểu của ngôn ngữ chủ để tạo cách diễn đạt gần với ngôn ngữ miền.

Ví dụ, một thư viện Kotlin có thể cung cấp DSL để khai báo tác vụ build:

```kotlin
tasks.register("packageApp") {
    dependsOn("compileApp")
    doLast {
        println("Packaging application")
    }
}
```

Đoạn mã vẫn tuân theo cú pháp Kotlin, nhưng các tên như `tasks`, `dependsOn` và `doLast` tạo thành từ vựng hướng đến miền build. Gradle Kotlin DSL là một ví dụ về cách tổ chức DSL nhúng.

| Tiêu chí | DSL bên ngoài | DSL nhúng |
|---|---|---|
| Cú pháp | Có thể thiết kế cú pháp riêng | Dựa trên cú pháp của ngôn ngữ chủ |
| Phân tích | Thường cần parser hoặc công cụ riêng | Thường tận dụng parser và compiler của ngôn ngữ chủ |
| Tích hợp | Cần cơ chế kết nối với chương trình và công cụ khác | Có thể gọi trực tiếp kiểu, hàm và thư viện của ngôn ngữ chủ |
| Trải nghiệm | Có thể gần với ngôn ngữ nghiệp vụ hơn | Có thể hưởng lợi từ IDE, kiểm tra kiểu và gỡ lỗi của ngôn ngữ chủ |
| Giới hạn | Phải xây dựng và duy trì cú pháp, công cụ riêng | Cú pháp bị giới hạn phần nào bởi ngôn ngữ chủ |

Không có lựa chọn luôn tốt hơn. DSL bên ngoài phù hợp khi cần cú pháp độc lập, dễ trao đổi giữa nhiều công cụ hoặc hướng đến người dùng không muốn viết bằng ngôn ngữ chủ. DSL nhúng phù hợp khi người dùng chủ yếu là lập trình viên và việc tích hợp với mã nguồn hiện có quan trọng.

### 1.3. Theo cách diễn đạt: khai báo và mệnh lệnh

**DSL khai báo** (*declarative DSL*) mô tả trạng thái, kết quả hoặc quy tắc mong muốn. Công cụ thực thi chịu trách nhiệm quyết định các bước cần thiết để đạt kết quả đó.

Ví dụ SQL:

```sql
SELECT name
FROM employees
WHERE department = 'Engineering';
```

Câu lệnh nêu dữ liệu cần lấy và điều kiện lọc. Người viết không phải chỉ rõ hệ quản trị cơ sở dữ liệu cần đọc từng trang dữ liệu theo thứ tự nào.

**DSL mệnh lệnh** (*imperative DSL*) mô tả các bước hoặc hành động cần thực hiện theo trình tự. Ví dụ, một DSL tự động hóa có thể cho phép khai báo lần lượt các bước tải dữ liệu, kiểm tra, chuyển đổi và lưu kết quả.

Một DSL cũng có thể pha trộn hai phong cách. Tệp cấu hình có thể khai báo trạng thái mong muốn, trong khi phần mở rộng cho phép viết các bước xử lý cụ thể. Vì vậy, nên xem khai báo và mệnh lệnh là một chiều thiết kế thay vì kết luận chỉ dựa trên tên gọi của ngôn ngữ.

### 1.4. Theo cách tương tác: văn bản và trực quan

**DSL dạng văn bản** biểu diễn chương trình bằng ký tự, từ khóa, biểu thức và cấu trúc văn bản. SQL, CSS, regex và HCL là các ví dụ quen thuộc. Văn bản thuận tiện cho quản lý phiên bản, tìm kiếm, so sánh thay đổi và tự động sinh nội dung.

**DSL trực quan** (*visual DSL*) biểu diễn mô hình bằng sơ đồ, khối, nút hoặc kết nối. Người dùng có thể kéo thả các thành phần để mô tả luồng công việc, quy trình nghiệp vụ, mạch logic hoặc luồng dữ liệu.

Ví dụ, trong công cụ tự động hóa quy trình, người dùng có thể nối các khối `Trigger`, `Filter`, `Transform` và `Send` để mô tả một luồng xử lý. Mỗi khối đại diện cho một thao tác trong miền.

DSL trực quan có thể giúp người dùng nhìn thấy quan hệ và luồng xử lý, nhưng cần thiết kế tốt để tránh sơ đồ quá lớn hoặc khó quản lý thay đổi. Một số hệ thống cho phép chuyển đổi qua lại giữa biểu diễn trực quan và văn bản để tận dụng ưu điểm của cả hai.

## 2. Mức độ mở của DSL

Ngoài cách phân loại theo hình thức, DSL còn khác nhau ở mức độ cho phép người dùng mở rộng.

**DSL đóng** cung cấp một tập cú pháp và khả năng được xác định trước. Người dùng có thể cấu hình dữ liệu đầu vào hoặc chọn các tùy chọn mà DSL đã hỗ trợ, nhưng không thể tự thêm cấu trúc hay hành vi mới vào ngôn ngữ.

**DSL có thể cấu hình** cho phép điều chỉnh tham số, khai báo biến, nạp tệp, tái sử dụng module hoặc kết hợp các thành phần đã có. Cách này mở rộng những trường hợp sử dụng mà không nhất thiết thay đổi cú pháp hoặc ngữ nghĩa của DSL.

**DSL có thể mở rộng** cung cấp giao diện hoặc cơ chế để bổ sung hành vi mới, chẳng hạn hàm, kiểu dữ liệu, toán tử, loại tài nguyên, quy tắc hoặc plugin. Mức mở rộng có thể chỉ nằm ở thư viện và API, hoặc đi sâu đến parser, bộ kiểm tra kiểu và runtime.

Ba mức trên là cách mô tả thực tế về thiết kế, không phải một chuẩn phân loại bắt buộc. Một DSL có thể đóng ở phần cú pháp nhưng mở ở phần hàm mở rộng; một DSL khác có thể cho phép plugin thêm tài nguyên nhưng vẫn giữ nguyên ngữ pháp.

## 3. Điểm mở rộng là gì?

**Điểm mở rộng** (*extension point*) là vị trí hoặc giao diện được thiết kế để bổ sung khả năng cho DSL mà không phải viết lại toàn bộ công cụ xử lý. Cơ chế mở rộng (*extension mechanism*) là cách người dùng hoặc nhà phát triển sử dụng điểm đó.

Ví dụ, một DSL triển khai pipeline dữ liệu có thể cung cấp điểm mở rộng để đăng ký phép biến đổi mới. Người dùng có thể thêm thao tác `normalize_dates` vào tập thao tác có sẵn. Khi pipeline gặp tên thao tác đó, engine gọi phần triển khai đã đăng ký.

Điểm mở rộng cần có hợp đồng rõ ràng: tên thao tác, kiểu đầu vào, kiểu đầu ra, tham số, cách báo lỗi và điều kiện thực thi. Nếu hợp đồng không rõ, các phần mở rộng dễ xung đột hoặc hoạt động khác nhau giữa các môi trường.

## 4. Các lớp điểm mở rộng phổ biến

Một DSL có thể hỗ trợ mở rộng ở nhiều lớp. Không phải DSL nào cũng cần tất cả các lớp này.

### 4.1. Mở rộng dữ liệu và cấu hình

Đây thường là mức đơn giản nhất. Người dùng có thể cung cấp giá trị, biến, tham số, bí danh, tệp cấu hình hoặc module tái sử dụng.

Ví dụ, một DSL cấu hình triển khai có thể cho phép khai báo môi trường:

```yaml
environment: staging
replicas: 3
region: asia-southeast1
```

Thay đổi giá trị giúp tái sử dụng cùng cấu trúc cho nhiều môi trường. Tuy nhiên, việc thay đổi cấu hình không đồng nghĩa với việc thêm cú pháp hoặc khả năng mới vào DSL.

### 4.2. Mở rộng thư viện, hàm và quy tắc miền

DSL có thể cho phép đăng ký hàm, bộ lọc, bộ kiểm tra hoặc quy tắc nghiệp vụ mới. Người dùng vẫn viết theo cú pháp hiện có, nhưng có thêm thao tác để sử dụng.

Ví dụ SQL hỗ trợ hàm do người dùng định nghĩa (*user-defined function – UDF*) trong nhiều hệ quản trị cơ sở dữ liệu. Hàm mới bổ sung phép tính hoặc thao tác có thể gọi trong câu truy vấn. Một số hệ quản trị còn hỗ trợ kiểu dữ liệu, toán tử hoặc thủ tục do người dùng định nghĩa.

Mở rộng bằng thư viện phù hợp khi cấu trúc ngôn ngữ đã đủ biểu đạt, nhưng tập thao tác có sẵn chưa đáp ứng mọi nhu cầu.

### 4.3. Mở rộng bằng module và template

Module cho phép gom các khai báo liên quan thành thành phần có thể nhập và tái sử dụng. Template hoặc macro có thể tạo ra cấu trúc lặp lại từ tham số.

Ví dụ, một DSL mô tả hạ tầng có thể cho phép đóng gói nhóm tài nguyên mạng thành module. Nhiều dự án gọi lại module với các tham số khác nhau thay vì sao chép toàn bộ khai báo.

Module giúp tổ chức và chia sẻ mô hình miền. Cần quản lý phiên bản, giao diện đầu vào và phụ thuộc để thay đổi một module không làm hỏng các nơi đang sử dụng nó.

### 4.4. Mở rộng cú pháp và ngữ nghĩa

Một số DSL cho phép thêm cấu trúc cú pháp, toán tử, biểu thức hoặc quy tắc mới. Đây là mức mở rộng sâu vì nó ảnh hưởng đến cách phân tích và hiểu chương trình DSL.

Ví dụ, một ngôn ngữ truy vấn có thể cho phép plugin đăng ký toán tử mới; một ngôn ngữ luật có thể cho phép định nghĩa cú pháp cho một loại điều kiện nghiệp vụ. Công cụ cần biết cách phân tích cấu trúc mới và cách kiểm tra ý nghĩa của nó.

Mở rộng cú pháp có thể làm ngôn ngữ linh hoạt hơn, nhưng cũng khiến tài liệu, trình định dạng, IDE, parser và công cụ kiểm tra phức tạp hơn. Nếu nhiều nhóm tự định nghĩa cú pháp khác nhau, mã DSL có thể khó đọc và khó trao đổi.

### 4.5. Mở rộng engine, backend và tích hợp

DSL có thể cho phép thêm bộ thực thi, bộ sinh mã, adapter hoặc kết nối đến hệ thống bên ngoài. Phần DSL mô tả ý định, còn backend mới quyết định cách chuyển ý định đó thành hành động trên một nền tảng cụ thể.

Ví dụ, một DSL pipeline có thể giữ nguyên mô tả các bước nhưng chạy trên engine cục bộ hoặc engine phân tán. Một DSL hạ tầng có thể dùng provider để bổ sung khả năng làm việc với một nền tảng đám mây hoặc dịch vụ mới.

Trong Terraform, provider bổ sung các loại tài nguyên và nguồn dữ liệu mà cấu hình HCL có thể tham chiếu. Provider mở rộng khả năng miền và tích hợp của công cụ; nó không có nghĩa là mỗi provider đều thêm cú pháp mới vào ngữ pháp HCL.

### 4.6. Mở rộng công cụ phát triển

Một DSL có thể hỗ trợ plugin cho IDE, trình định dạng, linter, kiểm tra tĩnh, gợi ý mã, tài liệu hoặc công cụ trực quan hóa. Các phần mở rộng này cải thiện trải nghiệm phát triển mà không nhất thiết thay đổi ngôn ngữ hay hành vi runtime.

Ví dụ, một DSL cấu hình có thể có linter kiểm tra tên tài nguyên không hợp lệ và plugin IDE cung cấp gợi ý các trường được phép. Những công cụ đó giúp phát hiện lỗi sớm, đặc biệt khi DSL được sử dụng trong nhiều dự án.

## 5. Ví dụ tổng hợp: DSL xử lý pipeline dữ liệu

Giả sử một nhóm xây dựng DSL nhỏ để mô tả quy trình xử lý dữ liệu. Cú pháp giả định dưới đây chỉ minh họa ý tưởng, không phải cú pháp của một công cụ cụ thể:

```text
pipeline "daily-report" {
    source "employees.csv"
    transform filter_department("Engineering")
    transform normalize_dates("yyyy-MM-dd")
    sink "report.parquet"
}
```

DSL có từ vựng thuộc miền pipeline: `pipeline`, `source`, `transform` và `sink`. Người viết mô tả nguồn, các bước chuyển đổi và đích lưu dữ liệu.

Ban đầu, engine chỉ hỗ trợ một số phép biến đổi tích hợp sẵn. Sau đó, nhóm có thể mở rộng theo nhiều cách:

| Nhu cầu | Điểm mở rộng | Kết quả |
|---|---|---|
| Thay đổi đường dẫn theo môi trường | Biến và tham số cấu hình | Cùng pipeline chạy với dữ liệu đầu vào khác nhau |
| Bổ sung thao tác chuẩn hóa mã nhân viên | Hàm hoặc transform do người dùng đăng ký | Có thêm phép biến đổi mà không đổi cấu trúc pipeline |
| Dùng lại nhóm bước làm sạch dữ liệu | Module hoặc template | Nhiều pipeline chia sẻ một quy trình chuẩn |
| Đọc dữ liệu từ kho đối tượng | Connector hoặc plugin nguồn dữ liệu | DSL hỗ trợ thêm loại nguồn |
| Chạy trên engine phân tán | Backend hoặc adapter thực thi | Giữ mô tả pipeline nhưng thay đổi môi trường chạy |
| Gợi ý tên transform trong IDE | Plugin công cụ phát triển | Người viết dễ khám phá khả năng đang có |

Ví dụ cho thấy mở rộng DSL không nhất thiết có nghĩa là thay đổi cú pháp. Nhiều nhu cầu có thể được giải quyết bằng cách bổ sung thư viện, module, connector hoặc backend. Chỉ khi cách diễn đạt hiện tại không thể biểu đạt một khái niệm mới thì mới cần xem xét mở rộng ngữ pháp.

## 6. Thiết kế điểm mở rộng có kiểm soát

Mở rộng giúp DSL thích nghi với nhiều tình huống, nhưng mỗi điểm mở rộng cũng tạo thêm hợp đồng mà công cụ phải duy trì. Một thiết kế tốt cần cân bằng khả năng tùy biến với tính nhất quán.

### 6.1. Xác định đúng lớp cần mở rộng

Trước tiên, xác định nhu cầu thuộc dữ liệu, thao tác miền, cấu trúc tái sử dụng, cú pháp, engine hay công cụ phát triển. Nếu chỉ cần một phép biến đổi mới, API đăng ký hàm có thể đủ; không cần thêm từ khóa hoặc sửa grammar.

### 6.2. Định nghĩa hợp đồng ổn định

Mỗi extension nên có quy tắc về:

- Tên và namespace để tránh trùng lặp.
- Kiểu và cấu trúc dữ liệu đầu vào, đầu ra.
- Tham số bắt buộc, giá trị mặc định và cách kiểm tra.
- Quy tắc báo lỗi và thông tin chẩn đoán.
- Phiên bản API, khả năng tương thích và cách nâng cấp.
- Quyền truy cập tài nguyên nếu extension có thể đọc tệp, gọi mạng hoặc thực hiện hành động bên ngoài.

Hợp đồng rõ ràng giúp extension có thể được phát triển và kiểm thử độc lập với phần lõi DSL.

### 6.3. Kiểm soát an toàn và độ tin cậy

Extension có thể thực thi mã hoặc truy cập hệ thống. Công cụ cần cân nhắc nguồn tin cậy, quyền hạn, giới hạn tài nguyên và khả năng cô lập. Với DSL cấu hình, cũng cần tránh để một plugin có thể âm thầm thay đổi ý nghĩa của cấu hình ở nơi khác.

Các quy tắc quan trọng nên được kiểm tra trước khi thực thi. Nếu DSL hướng đến kết quả có thể tái lập, cần quy định rõ cách xử lý thời gian, thứ tự, trạng thái dùng chung và phụ thuộc bên ngoài.

### 6.4. Giữ khả năng đọc và khả năng tương thích

Không nên để mỗi extension tự tạo một cách viết hoàn toàn khác cho cùng một khái niệm. Cần quy ước đặt tên, định dạng, tài liệu và thông báo lỗi thống nhất. Khi thay đổi API hoặc ngữ nghĩa, nên có phiên bản và lộ trình chuyển đổi để dự án cũ tiếp tục hoạt động trong khoảng thời gian phù hợp.

### 6.5. Chỉ mở rộng khi có nhu cầu thực tế

Một DSL nhỏ, có miền rõ ràng thường dễ học và dễ kiểm soát. Nếu mở rộng mọi lớp ngay từ đầu, hệ thống sẽ phải duy trì nhiều giao diện và quy tắc mà có thể không ai sử dụng. Nên bắt đầu từ các trường hợp sử dụng thực tế, quan sát phần nào thường xuyên thay đổi, rồi thiết kế điểm mở rộng ở phần đó.

## 7. Lựa chọn biến thể và chiến lược mở rộng

Khi thiết kế hoặc lựa chọn DSL, có thể dùng các câu hỏi sau để xác định hình thức phù hợp:

1. **Miền rộng đến đâu?** DSL phục vụ một ngành cụ thể hay một hoạt động dùng chung ở nhiều lĩnh vực?
2. **Ai là người viết?** Chuyên gia nghiệp vụ có cần đọc và sửa trực tiếp không, hay chủ yếu là lập trình viên?
3. **Cần tích hợp với mã nguồn thế nào?** Một cú pháp riêng có lợi hơn hay DSL nhúng trong ngôn ngữ hiện có sẽ thuận tiện hơn?
4. **Cần mô tả điều gì?** Người dùng chỉ khai báo trạng thái mong muốn hay cần điều khiển các bước thực thi?
5. **Cách biểu diễn nào phù hợp?** Văn bản có lợi cho quản lý phiên bản, còn biểu diễn trực quan có thể hữu ích với sơ đồ và quy trình?
6. **Điều gì cần thay đổi theo thời gian?** Tham số, thao tác miền, loại tài nguyên, cú pháp hay backend?
7. **Ai duy trì extension?** Có đội ngũ, tài liệu, kiểm thử và cam kết tương thích cho các phần mở rộng không?

Một DSL có thể kết hợp nhiều lựa chọn: ví dụ một DSL văn bản, bên ngoài, khai báo, có phạm vi ngang và mở rộng thông qua module cùng plugin. Việc chọn biến thể nên dựa trên người dùng, miền vấn đề, môi trường triển khai và chi phí duy trì.

## 8. Những nhầm lẫn cần tránh

**Mở rộng khả năng không đồng nghĩa với mở rộng cú pháp.** Thêm hàm, provider hoặc connector có thể bổ sung hành vi trong khi grammar vẫn giữ nguyên.

**Tham số cấu hình không phải lúc nào cũng là extension.** Thay đổi giá trị đầu vào thường chỉ tạo một cấu hình khác. Nó chỉ trở thành một cơ chế mở rộng theo nghĩa rộng khi DSL được thiết kế để người dùng bổ sung thành phần hoặc hành vi có thể tái sử dụng.

**DSL nhúng không phải chỉ là một thư viện thông thường.** Một API có thể tạo thành DSL nhúng khi nó cung cấp từ vựng, cấu trúc và cách kết hợp có chủ đích để diễn đạt một miền. Tuy nhiên, không phải mọi lời gọi hàm đều cần được xem là DSL.

**DSL mở rộng không có nghĩa là cho phép mọi thứ.** Một ngôn ngữ có thể mở ở lớp hàm và plugin nhưng vẫn giới hạn cú pháp, quyền truy cập và loại hành động để bảo đảm tính nhất quán.

**Nhiều biến thể có thể cùng tồn tại.** Một DSL vừa có thể là dọc, vừa là nhúng, vừa có phong cách khai báo và có plugin. Các nhãn này mô tả những chiều khác nhau của thiết kế.

## 9. Ghi nhớ

- DSL có thể được phân loại theo phạm vi miền, cách triển khai, phong cách diễn đạt và cách tương tác.
- DSL dọc tập trung vào một ngành hoặc miền nghiệp vụ; DSL ngang tập trung vào một hoạt động có thể dùng trong nhiều lĩnh vực.
- DSL bên ngoài có cú pháp và công cụ phân tích riêng; DSL nhúng tận dụng cú pháp của một ngôn ngữ chủ.
- Điểm mở rộng là giao diện được thiết kế để bổ sung dữ liệu, thao tác, module, cú pháp, backend hoặc công cụ.
- Mở rộng có kiểm soát cần hợp đồng rõ ràng, phiên bản, kiểm tra lỗi, giới hạn quyền và tài liệu.
- Chỉ nên mở rộng ở lớp giải quyết đúng nhu cầu; không phải mọi DSL đều cần plugin hoặc cú pháp có thể tùy biến.

## 10. Câu hỏi tự kiểm tra

1. DSL dọc và DSL ngang khác nhau ở cách xác định phạm vi miền như thế nào?
2. Nêu một ưu điểm và một giới hạn của DSL nhúng so với DSL bên ngoài.
3. SQL là ví dụ cho phong cách khai báo ở điểm nào?
4. Vì sao thêm một provider cho DSL hạ tầng không nhất thiết có nghĩa là thay đổi cú pháp của ngôn ngữ?
5. Phân biệt điểm mở rộng và cơ chế mở rộng bằng một ví dụ.
6. Một DSL pipeline cần hỗ trợ thao tác chuyển đổi dữ liệu mới. Nên cân nhắc mở rộng thư viện, cú pháp hay backend trong trường hợp nào?
7. Nêu ba điều cần quy định trong hợp đồng của một plugin để tránh lỗi tích hợp.
