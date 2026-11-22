# Quy tắc escape, xuống dòng và giữ nội dung Markdown dễ đọc

Springdoc lấy metadata từ annotation, model và cấu hình để tạo OpenAPI JSON/YAML. Các trường mô tả như **@Operation.description**, **@Parameter.description**, **@Schema.description** hoặc **@ApiResponse.description** có thể chứa Markdown để Swagger UI trình bày tài liệu dễ đọc hơn.

Khi viết những nội dung này, cần phân biệt các lớp xử lý: Java string literal, YAML scalar, JSON string và cú pháp Markdown. Mỗi lớp có quy tắc escape và xuống dòng riêng. Nếu dùng cú pháp của lớp này ở lớp khác, nội dung có thể hiện nguyên dấu gạch chéo, mất xuống dòng, làm hỏng JSON hoặc khiến Swagger UI hiển thị sai định dạng.

## 1. Bốn lớp cú pháp cần phân biệt

Một description có thể đi qua nhiều bước trước khi người dùng nhìn thấy:

~~~text
Java annotation / YAML source
          |
          v
Chuỗi String trong ứng dụng
          |
          v
OpenAPI model
          |
          v
JSON hoặc YAML được serialize
          |
          v
Swagger UI phân tích Markdown
          |
          v
Nội dung hiển thị trong trình duyệt
~~~

| Lớp | Ví dụ | Quy tắc chính |
| --- | --- | --- |
| Java source | "Dòng 1\nDòng 2" | Escape theo Java string literal |
| YAML source | description: "Dòng 1\nDòng 2" | Escape theo YAML double-quoted scalar |
| JSON output | "description": "Dòng 1\nDòng 2" | Escape dấu quote, backslash và ký tự điều khiển |
| Markdown | bold, danh sách, heading | Dùng cú pháp Markdown/CommonMark |

Không có một quy tắc escape duy nhất áp dụng cho cả bốn lớp. Hãy xác định nội dung đang được viết trong Java, YAML, JSON hay Markdown trước khi thêm dấu gạch chéo ngược.

## 2. Markdown trong OpenAPI description

OpenAPI cho phép dùng CommonMark trong các trường description. Springdoc có thể đưa nội dung mô tả từ annotation vào đặc tả; Swagger UI sau đó render Markdown theo khả năng của phiên bản giao diện.

Các trường thường có thể chứa mô tả:

- **@OpenAPIDefinition(info = @Info(description = ...))**: mô tả tài liệu API.
- **@Operation(description = ...)**: mô tả operation.
- **@Parameter(description = ...)**: giải thích parameter.
- **@Schema(description = ...)**: mô tả object hoặc property.
- **@ApiResponse(description = ...)**: giải thích response.
- **@SecurityScheme(description = ...)**: giải thích cơ chế bảo mật.

Nên dùng summary cho một câu ngắn nhận diện operation và dùng description cho hướng dẫn, điều kiện, ví dụ hoặc quy tắc chi tiết. Tránh nhồi nhiều đoạn Markdown vào summary vì giao diện có thể hiển thị summary ở những vị trí hẹp.

Ví dụ nội dung Markdown:

~~~~markdown
Tra cứu sách theo từ khóa.

**Quy tắc**

- q là từ khóa tìm kiếm.
- page bắt đầu từ 0.
- Nếu không có kết quả, API trả về danh sách rỗng.

Ví dụ request:

~~~http
GET /api/books?q=spring&page=0
~~~
~~~~

Đoạn trên có hai đoạn văn, một danh sách và một code block. Dòng trống giúp Markdown phân tách các khối rõ ràng.

## 3. Xuống dòng trong Markdown

Markdown không luôn xem một ký tự xuống dòng trong source là một lần xuống dòng hiển thị. Các dòng văn bản liền nhau trong cùng một paragraph thường được nối thành một dòng khi render.

Ví dụ source:

~~~markdown
Dòng đầu tiên
Dòng thứ hai
~~~

Thông thường, trình render hiển thị chúng như một đoạn văn liên tục. Nếu muốn bắt đầu paragraph mới, để một dòng trống:

~~~markdown
Dòng đầu tiên.

Dòng thứ hai.
~~~

Nếu thật sự cần hard line break trong cùng một paragraph, CommonMark cho phép hai dấu cách ở cuối dòng hoặc một backslash trước newline:

~~~markdown
Địa chỉ: 12 Nguyễn Huệ.  
Thành phố: Hồ Chí Minh.
~~~

Hoặc:

~~~markdown
Địa chỉ: 12 Nguyễn Huệ.\
Thành phố: Hồ Chí Minh.
~~~

Trong tài liệu kỹ thuật, nên ưu tiên paragraph riêng hoặc danh sách thay vì phụ thuộc vào hai dấu cách cuối dòng. Dấu cách cuối dòng khó nhìn thấy, dễ bị editor hoặc formatter xóa và có thể làm kết quả render thay đổi.

## 4. Escape ký tự đặc biệt của Markdown

Một số ký tự có ý nghĩa cú pháp trong Markdown: dấu sao, gạch dưới, dấu thăng, dấu lớn hơn, ngoặc vuông, ngoặc tròn, dấu pipe và dấu backslash. Khi muốn hiển thị chúng như văn bản thông thường, có thể escape bằng backslash hoặc đặt trong code span.

| Ký tự muốn hiển thị | Cách viết thường dùng | Kết quả |
| --- | --- | --- |
| Dấu sao | backslash + dấu sao | dấu sao |
| Dấu gạch dưới | backslash + gạch dưới | gạch dưới |
| Dấu thăng ở đầu dòng | backslash + dấu thăng | dấu thăng |
| Dấu lớn hơn | backslash + dấu lớn hơn | dấu lớn hơn |
| Dấu pipe trong bảng | backslash + dấu pipe | dấu pipe |
| Tên thuộc tính | springdoc.api-docs.path | springdoc.api-docs.path |

Nếu đang mô tả tên class, property, endpoint hoặc biểu thức có nhiều ký tự đặc biệt, code span thường dễ đọc và ít lỗi hơn việc escape từng ký tự.

Ví dụ:

~~~markdown
Thuộc tính `springdoc.api-docs.path` đổi URL của OpenAPI document.

Generic `List<String>` biểu diễn danh sách chuỗi.

| Header | Ý nghĩa |
| --- | --- |
| A \| B | Biểu thức có pipe |
~~~

Đối với dấu ngoặc nhọn hoặc dấu nhỏ hơn/lớn hơn như List&lt;String&gt;, code span giúp tránh việc trình render hiểu nhầm chúng là HTML tag.

## 5. Code span và code fence

Code span dùng một cặp backtick cho một đoạn ngắn trong dòng. Ví dụ source Markdown:

~~~markdown
Đặt `springdoc.swagger-ui.path=/docs` trong application.properties.
~~~

Code fence dùng để trình bày đoạn code nhiều dòng. Nên chỉ rõ ngôn ngữ để người đọc dễ nhận biết và renderer có thể tô màu cú pháp:

~~~~markdown
~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~
~~~~

Nếu nội dung code có sẵn ba dấu backtick liên tiếp, hãy dùng fence dài hơn hoặc dùng dấu ngã. Ví dụ:

~~~~~markdown
~~~~text
Nội dung ví dụ có chứa ba dấu backtick bên trong.
~~~~
~~~~~

Khi viết Java text block có chứa Markdown code fence, hãy chọn fence ngoài đủ khác để không đóng khối code quá sớm. Trong bài này, các ví dụ dùng fence dấu ngã để code bên trong có thể giữ nguyên cấu trúc.

Không cần escape dấu nháy, dấu gạch chéo hoặc dấu ngoặc trong một code fence Markdown. Nội dung trong code fence được xem là code mẫu, không được parse như cú pháp Markdown thông thường.

## 6. Escape chuỗi trong Java annotation

Annotation nhận giá trị chuỗi Java. Với string literal thông thường, các escape sequence được Java xử lý trước khi Springdoc nhận giá trị:

~~~java
@Operation(
    summary = "Tìm kiếm sách",
    description = "Tìm sách theo từ khóa.\n\n**Quy tắc:**\n- q không được để trống.\n- page bắt đầu từ 0."
)
~~~

Trong Java:

| Ký hiệu trong source | Ký tự trong String runtime |
| --- | --- |
| Một backslash theo sau bởi n | Line feed, xuống dòng |
| Một backslash theo sau bởi t | Tab |
| Hai backslash liên tiếp | Một dấu backslash |
| Backslash trước dấu nháy kép | Một dấu nháy kép |
| Hai backslash theo sau bởi n | Hai ký tự backslash và chữ n |

Điểm dễ nhầm là escape newline (một backslash theo sau bởi n) và chuỗi literal gồm hai backslash theo sau bởi n:

- Một backslash theo sau bởi n tạo một newline thực trong chuỗi runtime.
- Hai backslash theo sau bởi n tạo hai ký tự backslash và chữ n; khi render sẽ thấy nguyên văn backslash-n.

Nếu mục tiêu là xuống dòng trong description, dùng một backslash theo sau bởi n trong Java source. Nếu mục tiêu là minh họa chuỗi ký tự backslash-n, dùng hai backslash theo sau bởi n.

## 7. Dùng Java text block cho description nhiều dòng

Từ Java 15, text block giúp viết chuỗi nhiều dòng dễ đọc hơn:

~~~~java
@Operation(
    operationId = "searchBooks",
    summary = "Tìm kiếm sách",
    description = """
        Tìm sách theo từ khóa và phân trang.

        **Tham số**

        - q: từ khóa tìm kiếm.
        - page: số trang, bắt đầu từ 0.

        Ví dụ:

        ~~~http
        GET /api/books?q=spring&page=0
        ~~~
        """
)
~~~~

Text block là string literal và có thể dùng làm giá trị annotation khi thỏa điều kiện constant expression của Java. Nó giữ newline trong nội dung, nhưng Java vẫn xử lý indentation và escape sequence theo quy tắc text block.

Một số lưu ý:

- Các khoảng trắng thụt đầu dòng chung được loại bỏ theo vị trí closing delimiter.
- Dòng trống vẫn được giữ trong nội dung.
- Escape sequence như **\\n**, **\\\\** vẫn được Java xử lý.
- Vị trí closing delimiter ảnh hưởng đến phần indentation được loại bỏ.
- Không dùng tab và space lẫn lộn nếu muốn giữ căn lề chính xác.

Hãy đặt closing delimiter ở cột nhất quán và xem nội dung String cuối cùng khi có yêu cầu định dạng chặt chẽ.

Với Java 8 hoặc Java 11, có thể ghép các chuỗi:

~~~java
@Operation(
    description =
        "Tìm sách theo từ khóa.\n\n" +
        "**Tham số**\n\n" +
        "- q: từ khóa tìm kiếm.\n" +
        "- page: số trang bắt đầu từ 0."
)
~~~

Khi ghép chuỗi, mỗi đoạn cần có newline rõ ràng. Nếu chỉ nối các string mà không có **\n**, các đoạn sẽ dính liền nhau.

## 8. Escape trong YAML scalar

Khi viết OpenAPI YAML thủ công hoặc đưa mô tả vào một YAML source, có ba kiểu scalar thường gặp:

### Plain scalar

~~~yaml
description: Tìm kiếm sách theo từ khóa
~~~

Plain scalar phù hợp với một dòng đơn giản. Nếu nội dung chứa dấu hai chấm theo sau bởi khoảng trắng, ký tự comment hoặc cấu trúc Markdown phức tạp, nên dùng quoted scalar hoặc block scalar để tránh YAML parser diễn giải nhầm.

### Single-quoted scalar

~~~yaml
description: 'Chuỗi có "nháy kép" và backslash \n được giữ nguyên'
~~~

Trong single-quoted scalar, dấu backslash không dùng để escape newline. Muốn có dấu nháy đơn bên trong, viết hai dấu nháy đơn liên tiếp:

~~~yaml
description: 'Người dùng''s API'
~~~

### Double-quoted scalar

~~~yaml
description: "Dòng thứ nhất\nDòng thứ hai"
~~~

Double-quoted scalar hiểu các escape sequence của YAML. Một backslash theo sau bởi n được chuyển thành newline trong giá trị sau khi parse; hai backslash theo sau bởi n biểu diễn backslash và chữ n.

## 9. Dùng block scalar để giữ Markdown nhiều dòng trong YAML

Với description có heading, danh sách và code fence, block scalar thường dễ đọc và ít phải escape hơn:

~~~~yaml
description: |-
  Tra cứu sách theo từ khóa.

  **Quy tắc**

  - q là từ khóa tìm kiếm.
  - page bắt đầu từ 0.

  Ví dụ:

  ~~~http
  GET /api/books?q=spring&page=0
  ~~~
~~~~

Các ký hiệu block scalar:

| Cú pháp | Ý nghĩa |
| --- | --- |
| literal block | Giữ newline giữa các dòng và giữ một newline cuối theo quy tắc YAML |
| literal block với dấu trừ | Giữ newline bên trong nhưng bỏ newline cuối |
| literal block với dấu cộng | Giữ cả các newline cuối |
| folded block | Thường gộp newline giữa các dòng văn bản thành dấu cách |
| folded block với dấu trừ | Folded block và bỏ newline cuối |

Với Markdown, literal block thường phù hợp hơn folded block vì Markdown dựa vào dòng trống và cấu trúc từng dòng để nhận diện heading, list và code fence. Folded scalar có thể làm các dòng Markdown dính thành một paragraph.

Indentation của block scalar rất quan trọng. Nội dung phải thụt vào sâu hơn key description; nếu indentation không nhất quán, YAML có thể báo lỗi hoặc hiểu sai cấu trúc.

## 10. Escape JSON trong OpenAPI examples

OpenAPI JSON là JSON chuẩn. Trong một JSON string:

- Dấu nháy kép bên trong giá trị phải có một backslash đứng trước.
- Backslash trong giá trị phải được biểu diễn bằng hai backslash liên tiếp.
- Newline phải dùng một backslash theo sau bởi n, không chèn ký tự xuống dòng thô vào giữa JSON string.
- Tab và các ký tự điều khiển phải được escape.

Ví dụ JSON hợp lệ:

~~~json
{
  "description": "Dòng thứ nhất\nDòng thứ hai",
  "path": "C:\\docs\\openapi"
}
~~~

Sau khi JSON được parse, giá trị description chứa newline thực và path chứa một backslash ở mỗi vị trí phân cách thư mục.

Khi dùng @ExampleObject, giá trị value thường là chuỗi chứa JSON. Nếu dùng Java string thông thường, cần escape cả lớp Java lẫn lớp JSON:

~~~java
@ExampleObject(
    name = "book",
    value = "{\"title\":\"Spring Boot\",\"note\":\"Dòng 1\\nDòng 2\"}"
)
~~~

Ở đây:

1. Một backslash trước dấu nháy kép là escape của Java để tạo dấu quote trong chuỗi.
2. Hai backslash theo sau bởi n trong Java source tạo một backslash theo sau bởi n trong JSON text.
3. JSON parser sau đó chuyển escape newline trong JSON thành newline trong giá trị.

Đây là hai lớp escape lồng nhau. Nếu thiếu một lớp, Java có thể không biên dịch hoặc JSON example không hợp lệ.

## 11. Dùng Java text block cho JSON example

Text block giúp JSON dễ đọc vì không cần escape từng dấu nháy kép:

~~~java
@ExampleObject(
    name = "book",
    summary = "Ví dụ một cuốn sách",
    value = """
        {
          "id": 42,
          "title": "Spring Boot",
          "note": "Dòng 1\\nDòng 2",
          "path": "C:\\\\docs"
        }
        """
)
~~~

Trong ví dụ, hai backslash trước n trong Java text block tạo một backslash trước n trong JSON string. Tương tự, bốn dấu backslash trong source tạo hai dấu backslash trong JSON text, sau khi JSON parse sẽ còn một dấu backslash trong giá trị.

Không thay hai backslash trước n bằng một backslash trước n trong JSON example nếu mục tiêu là một chuỗi JSON có escape newline. Nếu Java xử lý escape newline trước, JSON text sẽ nhận newline thực nằm bên trong chuỗi được quote và trở thành JSON không hợp lệ.

## 12. Không nhầm newline thật với ký tự backslash-n

Hai nội dung sau khác nhau:

~~~text
Dòng 1
Dòng 2
~~~

và:

~~~text
Dòng 1\nDòng 2
~~~

Nội dung đầu chứa một ký tự newline giữa hai dòng. Nội dung sau chứa hai ký tự backslash và n. Tùy mục tiêu:

| Mục tiêu | Java source | Giá trị runtime |
| --- | --- | --- |
| Xuống dòng thật | Java source có một backslash trước n | Hai dòng |
| Hiện nguyên backslash-n | Java source có hai backslash trước n | Hai ký tự backslash và n |

Khi OpenAPI được serialize sang JSON, newline thật trong description sẽ được biểu diễn bằng escape **\n** trong JSON text. Đó là hành vi bình thường của JSON serializer; khi client parse JSON, giá trị description vẫn chứa newline thực.

Không nên nhìn chuỗi JSON thô rồi kết luận nội dung bị double-escape. Hãy parse JSON hoặc xem description trong Swagger UI để kiểm tra giá trị sau deserialize.

## 13. Dùng Markdown cho tên property và ký tự giống HTML

Các tên Java generic, biểu thức hoặc nội dung có dấu nhỏ hơn/lớn hơn nên được đặt trong code span:

~~~markdown
Handler trả về Mono<ServerResponse>.

Generic Map<String, Object> biểu diễn map có key dạng chuỗi.
~~~

Nếu viết trực tiếp &lt;ServerResponse&gt; ngoài code span, một số renderer có thể diễn giải thành HTML tag. Khi cần hiển thị ký tự angle bracket như văn bản, có thể dùng entity HTML:

~~~markdown
Biểu thức A &lt; B và C &gt; D.
~~~

Tránh chèn HTML tùy ý vào description. Swagger UI có thể sanitize hoặc xử lý HTML theo chính sách bảo mật của phiên bản; nội dung HTML không phải lúc nào cũng được render như mong đợi. Ưu tiên CommonMark và code span.

Trong bảng Markdown, ký tự pipe phân tách cột. Nếu giá trị chứa pipe, escape nó:

~~~markdown
| Header | Ý nghĩa |
| --- | --- |
| A \| B | Biểu thức có pipe |
~~~

Trong code fence, không cần escape pipe vì parser đang ở chế độ code.

## 14. Viết description dễ đọc trong Swagger UI

Một description tốt nên có cấu trúc phù hợp với lượng thông tin:

- Mở đầu bằng một hoặc hai câu nêu mục đích operation.
- Dùng heading nhỏ khi có nhiều nhóm quy tắc.
- Dùng danh sách cho điều kiện hoặc trình tự.
- Dùng bảng cho mapping tham số, mã lỗi hoặc giá trị enum.
- Dùng code fence cho request/response mẫu.
- Dùng inline code cho property, type, endpoint và giá trị kỹ thuật.
- Tách paragraph bằng dòng trống.

Ví dụ:

~~~java
@Operation(
    summary = "Tạo sách",
    description = """
        Tạo một cuốn sách mới trong catalog.

        **Điều kiện**

        - title không được để trống.
        - publicationYear không được lớn hơn năm hiện tại.

        **Kết quả**

        - 201: tạo thành công.
        - 400: dữ liệu đầu vào không hợp lệ.
        - 409: sách đã tồn tại.
        """
)
~~~

Không cần thêm nhiều heading cho một mô tả chỉ có vài câu. Ngược lại, description dài nên chia thành các phần nhỏ thay vì viết thành một khối văn bản liên tục.

## 15. Cấu trúc Markdown không nên bị phá bởi escape sai

Các lỗi định dạng thường đến từ việc escape sai lớp hoặc đặt newline không đúng:

| Mong muốn | Cách viết sai thường gặp | Cách viết phù hợp |
| --- | --- | --- |
| Hai paragraph | Chỉ xuống dòng một lần | Chèn một dòng trống |
| Markdown bold | Escape dấu sao quanh chữ | Viết bold trực tiếp |
| Code span | Escape mọi ký tự bên trong code | Dùng code span |
| Markdown list | Dùng chuỗi backslash-n hiển thị nguyên văn | Tạo newline thực ở String runtime |
| JSON example có newline | Chèn newline thô trong JSON string | Dùng JSON escape \n |
| YAML description nhiều dòng | Dùng plain scalar dài | Dùng literal block |
| Dấu pipe trong table cell | Viết giá trị có dấu pipe | Escape pipe hoặc dùng code span |
| Code fence chứa backtick | Dùng fence ngoài ngắn bằng fence trong | Dùng fence ngoài dài hơn hoặc dấu ngã |

Đừng escape toàn bộ nội dung Markdown trước khi đưa vào annotation. Nếu làm vậy, ký hiệu bold, danh sách hoặc code fence có thể hiện nguyên dạng thay vì được render.

## 16. Kiểm tra nội dung qua OpenAPI JSON/YAML

Sau khi khởi động ứng dụng, mở endpoint OpenAPI, thường là /v3/api-docs hoặc path được cấu hình bằng springdoc.api-docs.path.

Kiểm tra các trường:

- info.description cho mô tả tổng quan.
- description của từng operation trong paths.
- description của từng parameter.
- requestBody.description và requestBody.content cho request.
- description và content của từng response theo status code.
- description của schema và từng property trong components.schemas.

Nếu xem JSON thô, newline thường được serialize thành **\n**. Điều đó không có nghĩa là Swagger UI sẽ hiển thị hai ký tự backslash và n. Sau khi parse JSON, giá trị String chứa newline thực.

Với YAML output, block scalar có thể biểu diễn description nhiều dòng bằng literal style hoặc dạng tương đương tùy serializer. Không nên dựa vào cách serializer chọn quote hay block style để suy luận nội dung; hãy kiểm tra giá trị sau khi parse.

## 17. Kiểm tra kết quả trên Swagger UI

Sau khi xác nhận OpenAPI document có đúng nội dung, mở Swagger UI và kiểm tra:

1. Paragraph có được tách đúng không.
2. Heading và danh sách có hiển thị theo đúng cấp không.
3. Inline code có giữ nguyên tên property, type và endpoint không.
4. Code fence có giữ nguyên indentation và không bị đóng sớm không.
5. Bảng có đủ cột và không bị vỡ bởi dấu pipe trong nội dung không.
6. Dấu nhỏ hơn/lớn hơn có hiển thị như code hay bị diễn giải thành HTML không.
7. Dòng chứa backslash có hiển thị đúng số lượng ký tự không.
8. JSON example có thể copy và parse hợp lệ không.

Nếu OpenAPI JSON đúng nhưng UI hiển thị khác, vấn đề có thể nằm ở khả năng Markdown renderer hoặc sanitizer của Swagger UI. Hãy thử cú pháp CommonMark cơ bản trước khi dùng HTML hoặc extension riêng của renderer.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI hiện nguyên backslash-n | Java source dùng hai backslash trước n nên runtime nhận backslash và n | Dùng một escape newline nếu cần newline thật |
| Hai dòng bị dính thành một paragraph | Markdown source không có dòng trống | Chèn dòng trống giữa hai paragraph |
| Danh sách không render | Các item không có newline hoặc indentation sai | Dùng newline thật và prefix dấu gạch ngang |
| Bold hoặc heading hiện nguyên dấu sao/thăng | Đã escape cú pháp Markdown không cần thiết | Bỏ backslash trước ký hiệu Markdown |
| JSON example báo parse error | Escape Java và JSON bị lẫn | Kiểm tra JSON text sau khi Java tạo String |
| JSON có newline thô trong string | Java text block chuyển escape newline thành newline trước khi JSON parse | Dùng backslash kép trước n trong Java text block cho JSON escape |
| Backslash trong Windows path bị mất | Java hoặc JSON xử lý backslash như escape | Escape riêng từng lớp hoặc dùng text block đúng cách |
| YAML parse lỗi ở description | Plain scalar chứa dấu đặc biệt hoặc indentation sai | Dùng quoted scalar hoặc block scalar |
| Markdown YAML bị gộp dòng | Dùng folded scalar | Dùng literal block |
| Bảng bị lệch cột | Có dấu pipe chưa escape trong cell | Escape dấu pipe hoặc dùng code span phù hợp |
| Code block bị cắt giữa chừng | Fence bên trong trùng fence ngoài | Tăng độ dài fence ngoài hoặc đổi sang dấu ngã |
| HTML tag biến mất | Renderer sanitize HTML | Dùng CommonMark, code span hoặc entity HTML |

## 19. Quy ước đề xuất cho nhóm phát triển

Để tài liệu nhất quán giữa nhiều controller và module:

1. Viết description bằng câu ngắn, rõ mục đích và điều kiện sử dụng.
2. Dùng Java text block cho mô tả nhiều dòng nếu dự án dùng Java 15 trở lên.
3. Với Java cũ, ghép chuỗi và ghi rõ hai newline giữa các paragraph.
4. Dùng YAML block scalar literal khi lưu Markdown nhiều dòng trong OpenAPI YAML.
5. Dùng JSON escape đúng chuẩn trong @ExampleObject.value.
6. Chỉ escape ký tự khi cú pháp của lớp hiện tại yêu cầu.
7. Dùng code span cho tên kỹ thuật có ký tự đặc biệt.
8. Dùng code fence có ngôn ngữ và kiểm tra fence lồng nhau.
9. Tránh hard line break dựa trên trailing spaces.
10. Kiểm tra cả OpenAPI JSON/YAML và Swagger UI trước khi phát hành tài liệu.

## 20. Checklist trước khi hoàn tất description

- [ ] Đã xác định chuỗi đang viết ở lớp Java, YAML, JSON hay Markdown.
- [ ] Escape sequence được áp dụng đúng lớp, không escape hai lần.
- [ ] Java newline escape được dùng cho newline thật trong String.
- [ ] JSON string không chứa newline thô hoặc dấu quote chưa escape.
- [ ] YAML multiline description dùng block scalar phù hợp.
- [ ] Markdown có dòng trống giữa các paragraph.
- [ ] Heading, list, table và code fence có cấu trúc hợp lệ.
- [ ] Ký tự đặc biệt được escape hoặc đặt trong code span khi cần.
- [ ] Không phụ thuộc vào trailing spaces để tạo line break.
- [ ] Nội dung trong Java text block có indentation nhất quán.
- [ ] Đã kiểm tra giá trị description sau khi parse OpenAPI JSON/YAML.
- [ ] Swagger UI hiển thị đúng paragraph, list, table, code và example.

Escape và xuống dòng cần được xử lý theo đúng lớp cú pháp. Java quyết định String runtime, YAML/JSON quyết định cách lưu và truyền chuỗi, còn Markdown quyết định cách trình bày description. Khi dùng newline thật cho cấu trúc Markdown, escape JSON đúng chuẩn và tránh double-escape, tài liệu Springdoc sẽ dễ đọc trong Swagger UI và vẫn giữ được nội dung chính xác trong OpenAPI JSON/YAML.
