# Ví dụ DSL trong thực tế

## 1. DSL xuất hiện ở đâu?

Domain-Specific Language (DSL, ngôn ngữ chuyên biệt theo miền) là ngôn ngữ được thiết kế để diễn đạt một nhóm vấn đề trong một lĩnh vực cụ thể. Thay vì cung cấp mọi khả năng tính toán như một ngôn ngữ lập trình đa dụng, DSL tập trung vào những khái niệm và thao tác mà người làm việc trong lĩnh vực đó thường xuyên sử dụng.

Ta gặp DSL trong hầu hết các hệ thống phần mềm:

- Truy vấn và biến đổi dữ liệu: SQL, Elasticsearch Query DSL, jq.
- Tìm kiếm và xử lý văn bản: biểu thức chính quy (regular expressions).
- Trình bày giao diện: CSS.
- Khai báo hạ tầng: HashiCorp Configuration Language (HCL) của Terraform.
- Tự động hóa quy trình phát triển: DSL cấu hình build của Gradle và workflow của GitHub Actions.

Các ví dụ này cho thấy DSL không nhất thiết phải có cú pháp giống một ngôn ngữ lập trình truyền thống. Một DSL có thể dùng từ khóa, biểu thức, cấu trúc JSON, YAML hoặc một API được thiết kế để đọc gần với ngôn ngữ của lĩnh vực.

## 2. SQL: ngôn ngữ truy vấn cơ sở dữ liệu

SQL là ví dụ tiêu biểu của DSL hướng dữ liệu quan hệ. Người dùng mô tả dữ liệu cần lấy hoặc thay đổi; hệ quản trị cơ sở dữ liệu chịu trách nhiệm lập kế hoạch và thực hiện thao tác phù hợp.

Giả sử hệ thống bán hàng có hai bảng:

~~~sql
CREATE TABLE customers (
    id          BIGINT PRIMARY KEY,
    full_name   VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    status       VARCHAR(30) NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Yêu cầu nghiệp vụ là tìm những khách hàng có tổng giá trị đơn hàng đã hoàn tất lớn hơn 10 triệu đồng trong năm 2026. Có thể diễn đạt trực tiếp bằng SQL:

~~~sql
SELECT
    c.id,
    c.full_name,
    SUM(o.total_amount) AS completed_revenue
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE o.status = 'COMPLETED'
  AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2027-01-01 00:00:00'
GROUP BY c.id, c.full_name
HAVING SUM(o.total_amount) > 10000000
ORDER BY completed_revenue DESC;
~~~

Đọc truy vấn theo ngôn ngữ nghiệp vụ:

- FROM và JOIN xác định nguồn dữ liệu và quan hệ giữa khách hàng với đơn hàng.
- WHERE lọc từng dòng đơn hàng theo trạng thái và khoảng thời gian.
- GROUP BY gom các đơn hàng theo khách hàng.
- SUM tính tổng doanh thu của mỗi nhóm.
- HAVING lọc kết quả sau khi đã gom nhóm.
- ORDER BY sắp xếp khách hàng theo doanh thu giảm dần.

SQL có tính khai báo (declarative): truy vấn nêu kết quả mong muốn, còn bộ tối ưu hóa của cơ sở dữ liệu quyết định cách thực thi, chẳng hạn chọn chỉ mục hoặc thứ tự kết hợp bảng. Người viết vẫn cần hiểu mô hình dữ liệu, chỉ mục và kế hoạch truy vấn để bảo đảm hiệu năng.

Trong ứng dụng, nên truyền giá trị đầu vào qua tham số của câu lệnh đã chuẩn bị (prepared statement) hoặc cơ chế bind parameter tương ứng. Không ghép trực tiếp dữ liệu người dùng vào chuỗi SQL, vì cách đó dễ gây lỗi và SQL injection.

## 3. Biểu thức chính quy: mô tả mẫu văn bản

Biểu thức chính quy (regular expression, thường viết tắt là regex) là một DSL nhỏ để mô tả mẫu ký tự. Nó thường được dùng để kiểm tra định dạng, tìm kiếm, trích xuất hoặc thay thế văn bản.

Ví dụ, một hệ thống có mã đơn hàng theo quy ước ORD- + bốn chữ số + dấu gạch nối + hai chữ cái in hoa. Mẫu sau mô tả quy ước đó:

~~~regex
^ORD-\d{4}-[A-Z]{2}$
~~~

Ý nghĩa từng phần:

| Thành phần | Ý nghĩa |
|---|---|
| ^ | Bắt đầu chuỗi |
| ORD- | Chuỗi ký tự cố định |
| \d{4} | Đúng bốn chữ số |
| - | Dấu gạch nối |
| [A-Z]{2} | Đúng hai chữ cái in hoa từ A đến Z |
| $ | Kết thúc chuỗi |

Với mẫu này, ORD-2048-HN phù hợp, còn ORD-248-HN và xORD-2048-HN không phù hợp. Trong Java, có thể sử dụng regex như sau:

~~~java
import java.util.regex.Pattern;

public class OrderCodeValidator {
    private static final Pattern ORDER_CODE =
            Pattern.compile("^ORD-\\d{4}-[A-Z]{2}$");

    public static boolean isValid(String value) {
        return value != null && ORDER_CODE.matcher(value).matches();
    }
}
~~~

Regex hữu ích khi quy tắc có thể diễn đạt gọn bằng mẫu ký tự. Tuy nhiên, regex dài và nhiều nhánh có thể khó đọc, khó bảo trì. Với dữ liệu có cấu trúc lồng nhau hoặc quy tắc nghiệp vụ phức tạp, nên dùng parser hay mã kiểm tra có tên hàm rõ ràng. Cú pháp regex cũng có khác biệt giữa các môi trường như Java, JavaScript, .NET và PCRE; cần kiểm tra đúng engine đang sử dụng.

## 4. CSS: mô tả cách trình bày tài liệu

CSS (Cascading Style Sheets) là ngôn ngữ chuyên biệt để mô tả cách trình duyệt trình bày các phần tử của tài liệu, thường là HTML. CSS tập trung vào bộ chọn (selector), thuộc tính và giá trị hiển thị.

Ví dụ, một trang bán hàng muốn hiển thị thẻ sản phẩm với khoảng cách hợp lý, có hiệu ứng khi rê chuột và chuyển thành một cột trên màn hình hẹp:

~~~css
.product-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1.5rem;
}

.product-card {
    padding: 1rem;
    border: 1px solid #d8dee8;
    border-radius: 0.75rem;
    background: white;
    transition: box-shadow 160ms ease;
}

.product-card:hover {
    box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 12%);
}

@media (max-width: 640px) {
    .product-grid {
        grid-template-columns: 1fr;
    }
}
~~~

Trong ví dụ:

- .product-grid chọn phần tử có lớp product-grid và bố trí các phần tử con bằng CSS Grid.
- .product-card mô tả khoảng đệm, đường viền, bo góc và màu nền của thẻ.
- :hover áp dụng quy tắc khi con trỏ đang nằm trên thẻ.
- @media giới hạn một nhóm quy tắc theo điều kiện về kích thước màn hình.

CSS không mô tả thuật toán xử lý đơn hàng hay quy tắc lưu dữ liệu. Nó chỉ mô tả cách trình bày. Trình duyệt kết hợp các quy tắc theo cơ chế cascade, độ đặc hiệu (specificity), thứ tự khai báo và kế thừa để xác định kiểu cuối cùng của phần tử.

## 5. Terraform HCL: khai báo hạ tầng

Terraform dùng HashiCorp Configuration Language (HCL) để mô tả tài nguyên hạ tầng như mạng, máy ảo, cơ sở dữ liệu và quyền truy cập. Người vận hành khai báo trạng thái mong muốn; Terraform so sánh cấu hình với trạng thái hiện tại rồi tạo kế hoạch thay đổi.

Ví dụ đơn giản khai báo một nhóm bảo mật trên AWS:

~~~hcl
variable "vpc_id" {
  description = "ID của mạng VPC cần gắn nhóm bảo mật"
  type        = string
}

resource "aws_security_group" "web" {
  name        = "web-server"
  description = "Cho phép nhận lưu lượng HTTPS"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

output "security_group_id" {
  value = aws_security_group.web.id
}
~~~

Các khối variable, resource và output là những cấu trúc của HCL được Terraform diễn giải theo miền quản lý hạ tầng. resource mô tả tài nguyên cần quản lý, còn output công bố một giá trị để cấu hình khác hoặc người vận hành sử dụng.

Quy trình thường gặp là định dạng và kiểm tra cấu hình, chạy terraform plan để xem trước thay đổi, rồi mới chạy terraform apply khi kế hoạch đã được xem xét. Cấu hình hạ tầng cần được quản lý phiên bản; thông tin bí mật nên được cấp qua cơ chế phù hợp thay vì ghi trực tiếp vào tệp cấu hình.

## 6. Gradle Kotlin DSL: mô tả quy trình build

Gradle cung cấp DSL để khai báo plugin, thư viện phụ thuộc và các tác vụ build. Khi dùng Kotlin DSL, tệp cấu hình thường có phần mở rộng .gradle.kts; mã Kotlin gọi các API Gradle theo cách được thiết kế cho miền build phần mềm.

Ví dụ một module Java:

~~~kotlin
plugins {
    java
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đoạn cấu hình khai báo plugin Java, thông tin phiên bản, kho tải thư viện, thư viện dùng khi kiểm thử và nền tảng chạy JUnit. Gradle đọc cấu hình để xây dựng mô hình build và thực hiện các task tương ứng.

Đây là một ví dụ về DSL nhúng (embedded DSL): cú pháp Kotlin vẫn là Kotlin, nhưng các hàm và khối như plugins, repositories, dependencies được cung cấp để biểu đạt khái niệm của Gradle. Nhờ IDE hiểu Kotlin, người phát triển có thể nhận gợi ý mã và kiểm tra kiểu trong quá trình viết cấu hình.

## 7. Elasticsearch Query DSL: tìm kiếm tài liệu có cấu trúc

Elasticsearch cung cấp Query DSL dựa trên JSON để mô tả điều kiện tìm kiếm. Nó phù hợp với hệ thống tìm kiếm sản phẩm, log hoặc tài liệu có nhiều tiêu chí lọc.

Ví dụ tìm các đơn hàng có trạng thái completed, tổng tiền từ 1 triệu trở lên và được tạo trong tháng 10 năm 2026:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "completed" } },
        { "range": { "total_amount": { "gte": 1000000 } } },
        {
          "range": {
            "created_at": {
              "gte": "2026-10-01T00:00:00",
              "lt": "2026-11-01T00:00:00"
            }
          }
        }
      ]
    }
  },
  "sort": [
    { "created_at": { "order": "desc" } }
  ]
}
~~~

bool.filter kết hợp các điều kiện lọc; term so khớp một giá trị đã được lập chỉ mục; range giới hạn khoảng giá trị; sort quy định thứ tự kết quả. Query DSL dùng JSON làm hình thức biểu diễn, nhưng ý nghĩa của các khóa như bool, filter, term và range đến từ mô hình truy vấn của Elasticsearch.

Khi xây dựng truy vấn từ dữ liệu đầu vào, ứng dụng nên kiểm soát các trường mà người dùng được phép lọc và sắp xếp. Điều này giúp tránh truy vấn ngoài ý muốn và giữ hiệu năng ổn định.

## 8. GitHub Actions: mô tả workflow CI/CD

GitHub Actions dùng tệp YAML để khai báo workflow tự động hóa, chẳng hạn chạy kiểm thử khi có pull request hoặc build khi tạo bản phát hành. YAML là định dạng tuần tự hóa dữ liệu đa dụng; ngữ nghĩa workflow đến từ schema và quy tắc của GitHub Actions. Vì vậy, có thể xem cấu hình workflow là một DSL dựa trên YAML.

Ví dụ chạy kiểm thử dự án Java khi có pull request vào nhánh main:

~~~yaml
name: Java CI

on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run tests
        run: ./gradlew test
~~~

Workflow có các thành phần chính:

- on xác định sự kiện kích hoạt workflow.
- jobs chứa những công việc cần chạy.
- runs-on chọn môi trường thực thi job.
- steps liệt kê tuần tự các bước trong job.
- uses gọi một action có sẵn; run thực thi lệnh trong môi trường runner.

Nhờ cấu hình được lưu cùng mã nguồn, nhóm phát triển có thể xem xét thay đổi CI/CD qua pull request và tái sử dụng quy trình giữa các lần chạy. Khi workflow cần thông tin nhạy cảm, hãy dùng GitHub Secrets hoặc cơ chế cấp thông tin xác thực phù hợp.

## 9. jq: lọc và biến đổi JSON

jq là một ngôn ngữ nhỏ để truy vấn và biến đổi dữ liệu JSON. Công cụ này hữu ích khi xử lý phản hồi API, tệp cấu hình hoặc dữ liệu log trong dòng lệnh.

Giả sử tệp orders.json có nội dung:

~~~json
{
  "orders": [
    { "id": 101, "status": "completed", "total": 250000 },
    { "id": 102, "status": "pending", "total": 90000 },
    { "id": 103, "status": "completed", "total": 450000 }
  ]
}
~~~

Lệnh sau lấy mã và tổng tiền của các đơn đã hoàn tất:

~~~bash
jq '.orders[] | select(.status == "completed") | {id, total}' orders.json
~~~

Trong biểu thức jq, .orders[] lần lượt duyệt các phần tử trong mảng orders; select(...) giữ lại phần tử thỏa điều kiện; {id, total} tạo một đối tượng mới chỉ gồm hai trường cần thiết. Có thể ghép các bộ lọc và phép biến đổi thành một pipeline ngắn mà không cần viết một chương trình riêng.

## 10. DSL nhúng và DSL bên ngoài trong các ví dụ

Những DSL trên có thể được phân loại theo cách chúng được tích hợp vào ứng dụng:

| Loại | Đặc điểm | Ví dụ |
|---|---|---|
| DSL bên ngoài (external DSL) | Có cú pháp và cách phân tích riêng; thường được viết trong tệp hoặc chuỗi độc lập | SQL, regex, jq, HCL |
| DSL nhúng (embedded DSL) | Dựa trên cú pháp và hệ sinh thái của một ngôn ngữ chủ; thư viện cung cấp API chuyên biệt | Gradle Kotlin DSL |
| DSL khai báo dựa trên định dạng dữ liệu | Dùng định dạng như JSON hoặc YAML, trong đó schema và quy tắc của công cụ tạo nên ý nghĩa chuyên biệt | Elasticsearch Query DSL, GitHub Actions workflow |

Ranh giới giữa các nhóm có thể phụ thuộc cách nhìn. Ví dụ, CSS có cú pháp riêng nên thường được xem là DSL bên ngoài; workflow GitHub Actions dùng YAML nhưng không phải mọi tệp YAML đều là DSL. Chính ngữ cảnh và bộ quy tắc mà công cụ áp dụng mới tạo nên miền ý nghĩa.

HTML cũng thường được nhắc đến trong nhóm ngôn ngữ chuyên biệt cho web vì nó mô tả cấu trúc tài liệu bằng các phần tử như header, main, article và form. Tuy nhiên, HTML chính xác hơn là ngôn ngữ đánh dấu (markup language), không phải ngôn ngữ lập trình. Việc phân loại rộng hay hẹp tùy tài liệu; khi thảo luận kỹ thuật, nên nêu rõ đang dùng khái niệm DSL theo nghĩa rộng.

## 11. Cách chọn DSL phù hợp cho một công việc

Khi lựa chọn DSL, hãy bắt đầu từ loại vấn đề cần giải quyết và người sẽ đọc, viết, bảo trì cấu hình:

1. **Miền bài toán có rõ ràng không?** SQL phù hợp với truy vấn dữ liệu quan hệ; CSS phù hợp với trình bày; HCL phù hợp với khai báo hạ tầng.
2. **Người dùng mục tiêu có hiểu được cú pháp không?** Một DSL tốt giúp chuyên gia miền nghiệp vụ diễn đạt công việc bằng khái niệm quen thuộc.
3. **Công cụ có hỗ trợ đủ tốt không?** Cần xem xét IDE, kiểm tra lỗi, tài liệu, định dạng, gỡ lỗi, kiểm thử và khả năng tích hợp vào quy trình hiện tại.
4. **Quy tắc có thể kiểm soát được không?** DSL có thể giới hạn những thao tác được phép, nhưng hệ thống vẫn cần xác thực đầu vào, phân quyền và giới hạn tài nguyên.
5. **Chi phí học và bảo trì có hợp lý không?** Nếu DSL mới chỉ giải quyết một trường hợp nhỏ, một API rõ ràng hoặc cấu hình đơn giản có thể dễ bảo trì hơn việc tạo ngôn ngữ riêng.

Một DSL phù hợp thường giúp diễn đạt ngắn gọn hơn, giảm mã lặp và làm ý định của cấu hình dễ hiểu. Ngược lại, một DSL có cú pháp quá phức tạp, thông báo lỗi khó hiểu hoặc thiếu công cụ hỗ trợ sẽ làm tăng chi phí cho cả người viết lẫn người vận hành.

## 12. Tổng kết qua tình huống thực tế

Hãy hình dung một nhóm phát triển xây dựng dịch vụ thương mại điện tử. Trong cùng một hệ thống, nhóm có thể dùng:

- SQL để lấy doanh thu theo khách hàng từ cơ sở dữ liệu quan hệ.
- Regex để kiểm tra mã đơn hàng theo quy ước.
- CSS để trình bày danh sách sản phẩm trên trình duyệt.
- Elasticsearch Query DSL để tìm đơn hàng theo nhiều tiêu chí.
- jq để lọc nhanh phản hồi JSON khi điều tra lỗi.
- Gradle Kotlin DSL để khai báo thư viện và tác vụ build.
- Terraform HCL để mô tả tài nguyên hạ tầng.
- GitHub Actions workflow để tự động chạy kiểm thử và build.

Mỗi DSL giải quyết một phần công việc với từ vựng và quy tắc phù hợp với miền của nó. Một hệ thống thực tế thường kết hợp nhiều DSL; người phát triển cần hiểu DSL đang dùng, giới hạn của nó và cách nó tương tác với mã nguồn, dữ liệu hoặc hạ tầng xung quanh.

Khi gặp một cú pháp mới, hãy tự hỏi: nó mô tả miền nào, công cụ nào diễn giải nó, và cấu hình đó tạo ra hành vi gì? Trả lời được ba câu hỏi này sẽ giúp đọc tài liệu, viết cấu hình và xử lý lỗi hiệu quả hơn.
