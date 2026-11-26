# Tài liệu hóa ma trận tính năng theo phiên bản và store

## 1. Vì sao cần ma trận tính năng?

Module `SPRING_DATA_COMMONS` giúp người học hiểu các abstraction dùng chung của Spring Data: Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing. Các abstraction này tạo ra một cách diễn đạt quen thuộc giữa nhiều module, nhưng không bảo đảm mọi store có cùng hành vi, cùng giới hạn hoặc cùng tiến độ hỗ trợ AOT.

Trong chương **Phiên bản và AOT**, một công việc quan trọng là biến nhận định chung như “Spring Data hỗ trợ projection” thành thông tin có thể sử dụng để thiết kế và nâng cấp ứng dụng:

> Loại projection nào, trên module store nào, với tổ hợp phiên bản nào, trong chế độ chạy nào, được tài liệu công bố đến đâu và đã được dự án kiểm chứng bằng luồng nào?

**Ma trận tính năng** là tài liệu trả lời các câu hỏi ấy theo một cấu trúc thống nhất. Nó hỗ trợ lựa chọn giải pháp, đánh giá thay đổi phiên bản và xác định phần chưa biết trước khi triển khai.

Bài này hướng dẫn cách thiết kế và duy trì ma trận. Những bảng có dữ liệu giả định chỉ minh họa cách ghi nhận; chúng không công bố khả năng hỗ trợ thực tế của bất kỳ release hay store nào.

## 2. Hợp đồng chung không phải cam kết đồng nhất

Xét một repository có chữ ký:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface ProductRepository extends Repository<Product, Long> {

    Page<Product> findByStatus(ProductStatus status, Pageable pageable);
}
```

Chữ ký này dùng các kiểu thuộc Spring Data Commons. Để biết phương thức có hoạt động trong ứng dụng hay không, vẫn cần xem:

- Module store có hỗ trợ kiểu repository và keyword tương ứng không.
- `Product` được mapping như thế nào.
- Store thực hiện phân trang và lấy thông tin tổng số phần tử ra sao.
- Cấu hình repository, provider hoặc driver có phù hợp không.
- Đường thực thi này có được hỗ trợ trong môi trường AOT hoặc native đang dùng không.

Một interface biên dịch được chỉ chứng minh rằng các kiểu tham chiếu có mặt và chữ ký phù hợp với quy tắc của Java. Nó chưa chứng minh query sẽ được tạo đúng, database có thể thực thi hay artifact native chứa đủ metadata cần thiết.

Vì vậy, đơn vị của ma trận phải là **một khả năng cụ thể trong một phạm vi cụ thể**, không chỉ là một tên API.

| Nhận định quá rộng | Cách diễn đạt phù hợp để đưa vào ma trận |
| --- | --- |
| Hỗ trợ CRUD | Lưu entity mới với ID do store sinh và đọc lại theo ID |
| Hỗ trợ derived query | `findByStatus` với property enum và kiểu trả về được chỉ rõ |
| Hỗ trợ phân trang | `Page` có nội dung, tổng số phần tử và thứ tự xác định |
| Hỗ trợ projection | Interface projection đóng cho tập thuộc tính đã chọn |
| Hỗ trợ auditing | Ghi người sửa và thời gian sửa trên đường cập nhật đang dùng |
| Hỗ trợ AOT | Tính năng repository cụ thể chạy trên artifact được build bằng quy trình AOT đã xác định |

## 3. Phân biệt ba loại ma trận

### 3.1. Ma trận tương thích dependency

Ma trận này trả lời: các phiên bản có được thiết kế và quản lý để sử dụng cùng nhau không?

Thông tin cần quan tâm gồm Spring Boot nếu dự án dùng Boot, Spring Framework, Spring Data release train, Commons, module store, provider, driver và JDK. Dependency management hoặc BOM giúp chọn một tổ hợp được quản lý; kết quả resolve thực tế vẫn cần được ghi lại.

Không suy ra Commons có cùng chuỗi số phiên bản với Spring Boot. Release train và phiên bản của artifact cũng là những khái niệm cần được phân biệt.

### 3.2. Ma trận khả năng của tính năng

Ma trận này trả lời: với một tổ hợp dependency, module store công bố hỗ trợ điều gì, với điều kiện nào?

Ví dụ: loại projection, keyword của derived query, kiểu phân trang, cơ chế auditing hoặc một tối ưu repository AOT cụ thể. Nguồn chính là tài liệu của đúng release và module liên quan.

### 3.3. Ma trận kiểm chứng ứng dụng

Ma trận này trả lời: ứng dụng đã thực thi những khả năng nào trên môi trường nào, và kết quả ra sao?

Một tổ hợp được công bố hỗ trợ vẫn có thể thất bại trong ứng dụng vì cấu hình sai, thiếu mapping hoặc có custom code chưa phù hợp. Ngược lại, một thử nghiệm thành công với workaround không tự trở thành cam kết hỗ trợ của framework.

Có thể trình bày cả ba loại trong cùng một tài liệu, nhưng cần giữ ý nghĩa của chúng riêng biệt. Đặc biệt, không dùng một dấu tích duy nhất để thay thế cả “được công bố hỗ trợ” và “đã kiểm chứng thành công”.

## 4. Chọn các chiều của ma trận

Một ma trận đầy đủ có thể có nhiều chiều. Không nhất thiết biến mọi chiều thành một cột ngang rộng; có thể tách bảng môi trường và tham chiếu bằng mã.

| Chiều | Nội dung cần ghi | Lý do |
| --- | --- | --- |
| Tính năng | Hành vi quan sát được và phạm vi đầu vào | Tránh dùng nhãn quá rộng |
| Module store | JPA, JDBC, MongoDB, R2DBC hoặc module cụ thể khác | Hỗ trợ không tự lan giữa các store |
| Phiên bản Spring Data | Release train và artifact thực tế | Phân biệt các thế hệ tính năng |
| Spring Boot/Framework | Phiên bản được dùng thực tế | Ảnh hưởng cấu hình, dependency và AOT |
| Mô hình thực thi | Imperative hoặc reactive | API, kiểu kết quả và ngữ cảnh khác nhau |
| Chế độ artifact | JVM thông thường, JVM dùng artifact AOT hoặc native | Cần bằng chứng riêng cho môi trường đích |
| Hạ tầng store | Database/server, provider, driver, dialect nếu liên quan | Hành vi phụ thuộc nhiều hơn Commons |
| Mô hình dữ liệu | ID, mutable/immutable, converter và mapping quan trọng | Có thể thay đổi đường thực thi |
| Cấu hình | Repository scanning, auditing, profile hoặc extension liên quan | Cùng dependency chưa chắc cùng ứng dụng |
| Nguồn và bằng chứng | Tài liệu, điều kiện, lần kiểm chứng | Cho phép rà soát kết luận |

### Không rút gọn “store” thành một nhãn mơ hồ

Với JPA, cần tách module Spring Data JPA khỏi JPA provider và database. Với JDBC hoặc R2DBC, cần biết loại driver và database. Với MongoDB, cần xem cả driver và server khi chúng ảnh hưởng đến khả năng đang đánh giá.

Không phải hàng nào cũng cần mọi chi tiết. Nếu một yếu tố không ảnh hưởng đến kết luận, có thể đặt ở bảng môi trường chung. Khi yếu tố ấy trở thành điều kiện hỗ trợ, phải đưa nó vào phạm vi của hàng hoặc ghi chú rõ ràng.

## 5. Xác định đúng độ chi tiết của một hàng

Một hàng quá rộng sẽ che mất giới hạn; một hàng quá nhỏ sẽ làm tài liệu khó duy trì. Cách chọn thực tế là dùng một hành vi có thể kiểm chứng độc lập và có ý nghĩa với ứng dụng.

### Ví dụ phân rã projection

Không nên chỉ có hàng “Projection: Có”. Có thể tách thành:

| Khả năng | Phạm vi cần làm rõ |
| --- | --- |
| Interface projection đóng | Getter tương ứng trực tiếp với thuộc tính |
| Projection có expression | Cơ chế expression và dữ liệu được tham chiếu |
| DTO projection | Constructor hoặc cơ chế tạo DTO của store |
| Dynamic projection | Tập lớp được chọn qua tham số tại runtime |
| Projection trong native | Kiểu kết quả và đường tạo đối tượng được artifact đích đáp ứng |

Chỉ đưa các hàng ứng dụng thực sự sử dụng hoặc dự kiến sử dụng. Không cần liệt kê mọi biến thể của toàn bộ Spring Data để tạo cảm giác đầy đủ.

### Ví dụ phân rã phân trang

`Page`, `Slice` và các cơ chế scrolling không nên bị gộp thành một ô “pagination”. Chúng có kiểu kết quả, yêu cầu metadata và cách điều hướng khác nhau. Store và release quyết định hỗ trợ cụ thể.

Ngay cả trong một hàng `Page`, cần nêu sort mặc định, trường hợp dữ liệu rỗng và cách kiểm tra tổng số phần tử nếu những yếu tố này quan trọng với API.

## 6. Dùng hai nhóm trạng thái độc lập

### 6.1. Trạng thái được công bố hỗ trợ

| Giá trị | Ý nghĩa | Khi sử dụng |
| --- | --- | --- |
| `SUPPORTED` | Nguồn của đúng release xác nhận khả năng trong phạm vi đang xét | Có căn cứ rõ về store, phiên bản và điều kiện |
| `LIMITED` | Có hỗ trợ nhưng kèm giới hạn ảnh hưởng trực tiếp tới hàng | Phải ghi rõ phần được hỗ trợ và phần bị giới hạn |
| `UNSUPPORTED` | Có căn cứ xác nhận phạm vi này không được hỗ trợ | Không suy ra chỉ từ một lỗi của ứng dụng |
| `UNKNOWN` | Chưa có đủ căn cứ kết luận | Chưa tìm được nguồn phù hợp hoặc nguồn mâu thuẫn |
| `NOT_APPLICABLE` | Khả năng không có ý nghĩa trong phạm vi này | Có lý do giải thích vì sao hàng không áp dụng |

Không tìm thấy tính năng trong một bảng tóm tắt chưa đủ để ghi `UNSUPPORTED`. Tương tự, việc thấy kiểu `Pageable` trong Commons chưa đủ để ghi `SUPPORTED` cho mọi repository của mọi store.

### 6.2. Trạng thái kiểm chứng của dự án

| Giá trị | Ý nghĩa |
| --- | --- |
| `PASS` | Có lần thực thi thành công đáp ứng tiêu chí của hàng |
| `FAIL` | Đã thực thi và có kết quả trái tiêu chí hoặc lỗi cần phân tích |
| `NOT_RUN` | Chưa thực thi trên đúng môi trường và artifact |
| `BLOCKED` | Chưa thể thực thi vì một điều kiện cụ thể chưa đáp ứng |
| `NOT_APPLICABLE` | Không yêu cầu thực thi cho hàng không áp dụng, kèm lý do |

Một số tổ hợp hoàn toàn hợp lý:

| Công bố hỗ trợ | Kiểm chứng | Cách đọc |
| --- | --- | --- |
| `SUPPORTED` | `NOT_RUN` | Có cơ sở tài liệu nhưng chưa có bằng chứng của ứng dụng |
| `SUPPORTED` | `FAIL` | Phải điều tra lỗi cấu hình, implementation hoặc môi trường |
| `LIMITED` | `PASS` | Chỉ xác nhận kịch bản nằm trong phạm vi giới hạn đã ghi |
| `UNKNOWN` | `PASS` | Thử nghiệm thành công, chưa đủ căn cứ gọi là hỗ trợ chính thức |
| `UNSUPPORTED` | `NOT_RUN` | Không cần làm thử để thay thế một giới hạn đã được xác nhận, trừ khi có mục tiêu nghiên cứu riêng |

Nếu dùng một extension hoặc workaround, ghi nó thành điều kiện hoặc biến thể riêng. Không đổi ô hỗ trợ chính thức chỉ vì một implementation tùy chỉnh đã chạy được.

## 7. Tách bảng môi trường khỏi bảng tính năng

### 7.1. Bảng môi trường

Có thể định danh mỗi tổ hợp bằng một mã như `ENV-HIEN-TAI-JVM` hoặc `ENV-MUC-TIEU-NATIVE`. Mã chỉ là tham chiếu; nội dung phải có phiên bản cụ thể trước khi kết luận thực tế.

| Trường | Cách ghi |
| --- | --- |
| Mã môi trường | Một mã ổn định trong tài liệu |
| Trạng thái môi trường | Đã chốt hoặc còn là phương án dự kiến |
| JDK | Phiên bản và distribution nếu liên quan |
| Spring Boot | Phiên bản thực tế, hoặc ghi rõ không dùng |
| Spring Framework | Phiên bản artifact đã resolve |
| Spring Data release train | Giá trị của tổ hợp đang dùng |
| Commons và module store | Tên artifact cùng phiên bản đã resolve |
| Provider/driver/server | Phiên bản của các thành phần liên quan |
| Chế độ chạy | JVM, JVM với AOT hoặc native |
| Công cụ AOT/native | Tên, phiên bản và cấu hình quan trọng |
| Bản ứng dụng | Revision hoặc định danh artifact có thể truy vết |
| Cấu hình dữ liệu | Mapping, converter, profile và đặc điểm dataset cần thiết |

Trong giai đoạn thiết kế, ô phiên bản có thể ghi “chưa chốt”. Khi đó, môi trường này chưa đủ điều kiện làm bằng chứng về một tổ hợp phiên bản cụ thể. Không thay thông tin thiếu bằng các từ “latest”, “mới nhất” hoặc chỉ ghi một major version rồi coi là đã cố định môi trường.

### 7.2. Bảng tính năng

Một bảng tối thiểu có thể gồm:

| Cột | Nội dung |
| --- | --- |
| Mã khả năng | Định danh ổn định của hành vi |
| Mô tả và điều kiện | Điều muốn khẳng định, đầu vào và phạm vi |
| Môi trường | Tham chiếu bảng môi trường |
| Công bố hỗ trợ | Một trạng thái trong nhóm hỗ trợ |
| Giới hạn | Điều kiện bắt buộc hoặc phần bị loại khỏi kết luận |
| Nguồn | Tài liệu của đúng release và vị trí liên quan |
| Kiểm chứng | Một trạng thái trong nhóm thực thi |
| Bằng chứng | Lần chạy, artifact và kết quả đáp ứng tiêu chí |
| Ngày rà soát/người phụ trách | Thông tin phục vụ cập nhật |

Không bắt buộc dồn mọi nội dung vào một bảng khổng lồ. Có thể để bảng tóm tắt ngắn và đặt mô tả chi tiết dưới từng mã khả năng trong cùng tài liệu.

## 8. Ví dụ một ma trận được trình bày đúng cách

**Toàn bộ trạng thái trong ví dụ này là giả định**, dùng để học cách đọc bảng. `ENV-A-JVM` và `ENV-A-NATIVE` đại diện cho hai môi trường đã được cố định trong một dự án giả định; chúng không phải chứng nhận cho phiên bản Spring Data nào.

| Mã | Khả năng | Môi trường | Công bố hỗ trợ giả định | Kiểm chứng giả định | Giới hạn/bằng chứng cần xem |
| --- | --- | --- | --- | --- | --- |
| `CRUD-ID` | Lưu entity mới, nhận ID rồi đọc lại | `ENV-A-JVM` | `SUPPORTED` | `PASS` | Chỉ loại ID và mapping được mô tả |
| `QUERY-STATUS` | Derived query theo `status` | `ENV-A-JVM` | `SUPPORTED` | `PASS` | Kiểm tra dữ liệu khớp và không khớp |
| `PAGE-SORT` | `Page` với sort theo thời gian và ID | `ENV-A-JVM` | `SUPPORTED` | `PASS` | Có tổng số phần tử; thứ tự ổn định trên dataset thử |
| `DTO-NATIVE` | DTO projection trong native | `ENV-A-NATIVE` | `UNKNOWN` | `NOT_RUN` | Chưa có nguồn phù hợp và chưa chạy |
| `AUDIT-UPDATE` | Ghi người sửa khi cập nhật | `ENV-A-JVM` | `SUPPORTED` | `FAIL` | Luồng thực tế thiếu auditor; cần điều tra |
| `DYNAMIC-TYPE` | Dynamic projection với một tập kiểu cố định | `ENV-A-NATIVE` | `LIMITED` | `BLOCKED` | Chưa có artifact native để kiểm chứng |

Các kết luận đúng từ bảng giả định:

- `AUDIT-UPDATE` thất bại chưa đủ để viết “store không hỗ trợ auditing”. Cần tìm nguyên nhân của luồng thực tế.
- `DTO-NATIVE` chưa được kiểm chứng; không được mượn kết quả projection trên JVM để đổi thành `PASS`.
- `DYNAMIC-TYPE` chưa có lần chạy nên chưa thể chứng minh ứng dụng đáp ứng giới hạn được công bố.
- `CRUD-ID` chỉ đại diện cho cách sinh ID và mapping đã mô tả, không đại diện cho mọi entity.

Các kết luận sai gồm “native đã được hỗ trợ toàn bộ” hoặc “chỉ cần CRUD chạy là mọi repository đều ổn”.

## 9. Tổ chức nguồn và bằng chứng

### 9.1. Nguồn cho mức hỗ trợ

Khi áp dụng vào dự án, ưu tiên các nguồn chính thức tương ứng với đúng release:

1. Reference documentation của Commons và module store.
2. Release notes, migration guide và tài liệu AOT/native của phiên bản đó.
3. Tài liệu provider, driver hoặc database khi chúng quyết định khả năng.
4. API documentation cho hợp đồng cụ thể.
5. Thông tin issue hoặc thay đổi chính thức nếu cần giải thích giới hạn chưa được tổng hợp đầy đủ.

Không dùng API documentation của Commons làm bằng chứng duy nhất cho cách store dịch query. Một issue đã được đóng cũng chưa đủ chứng minh bản vá có mặt trong artifact dự án đang dùng; cần biết release chứa thay đổi đó.

Mỗi nguồn nên ghi:

- Tiêu đề và đường dẫn trực tiếp tới trang hoặc mục liên quan.
- Phiên bản mà nguồn mô tả.
- Điều kiện hoặc giới hạn rút ra từ nguồn.
- Ngày truy cập hoặc ngày rà soát.

Nếu nguồn là trang thay đổi liên tục, phải nhận biết điều đó và ưu tiên bản tài liệu theo phiên bản khi có. Đường dẫn chỉ tới trang chủ dự án thường không đủ để người khác kiểm tra một kết luận cụ thể.

### 9.2. Bằng chứng cho trạng thái kiểm chứng

Một bằng chứng thực thi nên trả lời:

- Đã chạy kịch bản nào, với đầu vào và kỳ vọng nào?
- Chạy trên mã nguồn hoặc artifact nào?
- Môi trường, dependency và cấu hình nào được dùng?
- Kết quả quan sát là gì?
- Có giới hạn nào của dataset hoặc kịch bản không?

Log “application started” chỉ chứng minh ứng dụng đã khởi động qua một đường nhất định. Nó chưa chứng minh một custom fragment, converter hay projection đã được thực thi.

Với repository reactive, tạo một publisher chưa bảo đảm query đã chạy. Bằng chứng phải bao gồm việc subscribe và quan sát kết quả hoặc lỗi của luồng được xét.

### 9.3. Khi nguồn và thực nghiệm mâu thuẫn

Giữ nguyên cả hai loại thông tin và mô tả mâu thuẫn. Ví dụ:

> Tài liệu của release xác nhận hỗ trợ kịch bản này, nhưng lần chạy của ứng dụng thất bại khi tạo DTO. Chưa xác định nguyên nhân; cần kiểm tra constructor, mapping và metadata của artifact đích.

Không xóa nguồn để làm bảng “đẹp”, cũng không bỏ qua lỗi thực tế chỉ vì tài liệu ghi hỗ trợ.

## 10. Ghi một bản mô tả chi tiết cho khả năng

Sau đây là cấu trúc minh họa cho một bản ghi bên trong tài liệu. Các giá trị đặt trong dấu `<...>` là thông tin cần điền khi sử dụng thực tế, không phải phiên bản hay bằng chứng đã có.

```yaml
capabilityId: PAGE-STATUS
behavior: "Lấy trang sản phẩm theo status với thứ tự ổn định"
environmentId: "<mã môi trường đã cố định>"
scope:
  storeModule: "<module Spring Data đang dùng>"
  repositoryModel: "imperative"
  resultType: "Page<Product>"
  criteria: "status bằng tham số đầu vào"
  ordering: "createdAt giảm dần, id giảm dần"
  assumptions: "dataset không bị thay đổi trong lần kiểm chứng"
  exclusions: "không khẳng định hiệu năng với offset lớn"
declaredSupport:
  state: UNKNOWN
  source: null
  sourceVersion: null
  conditions: []
verification:
  state: NOT_RUN
  applicationRevision: null
  artifactId: null
  evidence: null
  checkedAt: null
maintenance:
  owner: "<nhóm phụ trách>"
  reviewTrigger: "thay đổi dependency, store hoặc query"
```

Cấu trúc này có một số điểm có chủ ý:

- `UNKNOWN` diễn đạt thiếu căn cứ, không tự đổi thành “không hỗ trợ”.
- `NOT_RUN` giữ nguyên sự thật rằng chưa có lần kiểm chứng.
- `null` biểu diễn thông tin chưa có thay vì bịa một đường dẫn bằng chứng.
- `scope` giúp một lần `PASS` không bị diễn giải vượt khỏi kịch bản.
- `exclusions` tách những điều chưa được kết luận, như hiệu năng offset lớn.

Định dạng Markdown, YAML hoặc một công cụ tài liệu khác chỉ là cách biểu diễn. Giá trị của ma trận nằm ở việc phạm vi, nguồn và bằng chứng có rõ ràng hay không.

## 11. Áp dụng cho các nhóm abstraction của Commons

### 11.1. Repository và CRUD

Ghi rõ domain type, ID type và hành vi được kiểm chứng: lưu mới, cập nhật, đọc, xóa hoặc optimistic locking nếu ứng dụng dùng. Đừng gộp mọi thao tác vào một ô `save` chạy thành công.

Với mô hình immutable, giá trị repository trả về có thể quan trọng đối với luồng tiếp theo. Ma trận nên mô tả cách ứng dụng sử dụng kết quả thay vì chỉ kiểm tra đối tượng đầu vào.

### 11.2. Derived queries

Ghi keyword, property path, kiểu tham số và kiểu kết quả. Một query theo thuộc tính đơn giản không chứng minh hỗ trợ mọi keyword hoặc quan hệ lồng nhau.

Nếu có xử lý tên phương thức bằng AOT, ghi chính xác loại query được đánh giá. Khả năng xử lý một derived query không đủ đại diện cho mọi query khai báo hoặc custom fragment.

### 11.3. Phân trang, sắp xếp và scrolling

Phân biệt `Page`, `Slice` và cơ chế scrolling được dùng. Với `Page`, tiêu chí có thể gồm nội dung và tổng số phần tử. Với sort, ghi tập thuộc tính cho phép và quy tắc xử lý giá trị trùng nhau nếu nghiệp vụ cần thứ tự ổn định.

Một lần chạy đúng trên dataset nhỏ không chứng minh truy vấn offset lớn đạt yêu cầu hiệu năng. Nếu hiệu năng là tiêu chí, cần hàng hoặc bằng chứng riêng với dataset và chỉ số đo phù hợp.

### 11.4. Projection

Ghi rõ interface projection, DTO projection, projection có expression hay dynamic projection. Với dynamic projection, nêu tập kiểu được ứng dụng cho phép chọn.

Không dùng một lần tạo entity thành công làm bằng chứng cho đường tạo DTO. Trong native image, các đường khởi tạo hoặc proxy khác nhau có thể có nhu cầu metadata khác nhau.

### 11.5. Auditing

Nêu thao tác tạo hay cập nhật, trường thời gian, kiểu auditor và nguồn ngữ cảnh. Kiểm chứng ghi được timestamp chưa chứng minh đã ghi đúng người sửa.

Với mô hình reactive, điều kiện về ngữ cảnh xác định auditor phải phù hợp đường thực thi reactive. Kết quả của một cấu hình imperative không được chuyển nguyên thành bằng chứng cho cấu hình reactive.

### 11.6. Mapping, generated accessor và AOT

Tách các khả năng sau nếu dự án cần đánh giá:

- Chuẩn bị cấu hình và metadata bằng Spring AOT.
- Khởi tạo hạ tầng repository trong artifact đích.
- Tối ưu hoặc sinh artifact cho query mà module store hỗ trợ.
- Tạo entity và truy cập thuộc tính qua cơ chế mapping tương ứng.
- Custom converter, resource hoặc reflection của mã ứng dụng.

Có generated accessor không tự chứng minh toàn bộ repository đã được xử lý tại build time. Với JPA, cần phân biệt trách nhiệm materialization của provider với hạ tầng chung của Commons.

## 12. Dùng ma trận để đánh giá nâng cấp

Một thay đổi phiên bản không chỉ là cập nhật một con số ở đầu tài liệu. Nó tạo ra một môi trường mới cần được so sánh với môi trường hiện tại.

Quy trình hợp lý:

1. **Giữ lại mốc hiện tại.** Ghi đủ môi trường và bằng chứng đang có.
2. **Định danh môi trường mục tiêu.** Chốt dependency, provider, driver và chế độ artifact dự kiến.
3. **Đọc thay đổi có liên quan.** Tìm giới hạn, API thay đổi, hỗ trợ mới hoặc yêu cầu cấu hình ảnh hưởng các hàng đang dùng.
4. **Đánh dấu phạm vi cần kiểm chứng lại.** Giữ kết quả cũ như bằng chứng lịch sử, không gán nó cho tổ hợp mới.
5. **Thực thi các luồng liên quan.** Ưu tiên tính năng thay đổi, custom code và đường triển khai đích.
6. **Cập nhật kết luận.** Ghi kết quả mới, giới hạn còn lại và quyết định áp dụng.

Không bắt buộc kiểm tra lại mọi khả năng không liên quan sau mỗi thay đổi nhỏ. Tuy nhiên, khi tổ hợp môi trường thay đổi, phải nói rõ bằng chứng cũ còn giá trị tham khảo hay đã được xác nhận lại trên tổ hợp mới.

### Ví dụ tác động của các loại thay đổi

| Thay đổi | Những phần nên rà soát |
| --- | --- |
| Nâng Commons cùng module store theo tổ hợp mới | Hợp đồng dùng thực tế, repository initialization và query liên quan |
| Thay provider hoặc driver | Mapping, transaction, kiểu dữ liệu và hành vi database |
| Chuyển JVM sang native | Hint, proxy, reflection, resource và custom code |
| Thêm dynamic projection | Tập kiểu kết quả và đường tạo đối tượng |
| Thay mutable entity bằng immutable entity | Constructor, mapping, ID và kết quả trả về sau lưu |
| Thêm auditing theo người dùng | Nguồn auditor, ngữ cảnh và thao tác tạo/cập nhật |
| Thay store | Toàn bộ giả định về query, mapping và tính năng phụ thuộc store |

Bảng tác động giúp tập trung công việc. Nó không thay thế tài liệu migration của release hoặc các điều kiện cụ thể của ứng dụng.

## 13. Những lỗi tài liệu thường gặp

| Lỗi | Vì sao gây hiểu nhầm | Cách sửa |
| --- | --- | --- |
| Một cột “Spring Data” cho mọi phiên bản | Che mất thời điểm có tính năng và thay đổi hành vi | Gắn kết luận với tổ hợp phiên bản |
| Chỉ ghi `Yes/No` | Trộn hỗ trợ chính thức, thử nghiệm và giới hạn | Tách trạng thái hỗ trợ với kiểm chứng |
| Mặc định mọi store có cùng API nên cùng khả năng | Commons không quyết định mọi query hoặc mapping | Kiểm tra module store cụ thể |
| Dùng tài liệu hiện tại cho bản cũ | Kết luận có thể mô tả tính năng chưa có ở bản đang dùng | Chọn tài liệu đúng release |
| Ghi `PASS` sau khi chỉ build thành công | Chưa thực thi hành vi cần kết luận | Gắn bằng chứng với luồng dữ liệu |
| Sao chép kết quả JVM sang native | Hai artifact có điều kiện runtime khác nhau | Tạo phạm vi và bằng chứng riêng |
| Đánh `UNSUPPORTED` khi chưa tìm được nguồn | Biến thiếu thông tin thành kết luận phủ định | Dùng `UNKNOWN` và ghi việc cần xác minh |
| Đánh `SUPPORTED` sau khi dùng custom fragment | Thành công có thể đến từ mã bổ sung của ứng dụng | Ghi riêng điều kiện hoặc biến thể có extension |
| Dùng `NOT_APPLICABLE` cho lỗi khó xử lý | Che giấu phần chưa giải quyết | Dùng `FAIL`, `BLOCKED` hoặc `UNKNOWN` đúng nghĩa |
| Không ghi revision và môi trường | Không thể tái lập bằng chứng | Bổ sung định danh artifact và điều kiện chạy |
| Ghi cả major version là phạm vi đã kiểm chứng | Mở rộng kết luận vượt khỏi lần chạy thật | Ghi phiên bản cụ thể hoặc căn cứ cho khoảng hỗ trợ |

## 14. Duy trì ma trận mà không biến nó thành gánh nặng

Nên duy trì một nguồn tài liệu chính và tham chiếu tới bằng chứng ở nơi thích hợp. Tránh sao chép cùng một ma trận vào nhiều tài liệu rồi cập nhật lệch nhau.

Một số nguyên tắc thực tế:

- Chỉ theo dõi các khả năng đang dùng hoặc đã có kế hoạch dùng.
- Dùng bảng môi trường để tránh lặp phiên bản dài trong mọi hàng.
- Giữ mã khả năng ổn định để lịch sử thay đổi còn có nghĩa.
- Cập nhật khi dependency, cấu hình, mapping hoặc đường triển khai thay đổi.
- Ghi ngày rà soát và nhóm phụ trách theo quy ước của dự án.
- Giữ bằng chứng cũ với môi trường cũ thay vì sửa lịch sử thành kết quả mới.
- Nếu tự động tổng hợp dữ liệu dependency hoặc kết quả chạy, vẫn cần con người đánh giá phạm vi và giới hạn.

Trình tổng hợp có thể đọc được một phiên bản artifact; nó không tự hiểu rằng một DTO projection có expression nằm ngoài phạm vi đã được kiểm chứng. Vì vậy, tự động hóa thích hợp để thu thập dữ liệu và phát hiện thay đổi, còn kết luận hỗ trợ cần dựa trên ngữ nghĩa của tính năng.

## 15. Tình huống thực hành

Một nhóm đang có API sản phẩm chạy trên JVM và muốn nâng phiên bản đồng thời chuyển sang native. API dùng derived query theo `status`, `Page` có sort, DTO projection và auditing người sửa.

Nhóm đề xuất một bảng ban đầu:

| Tính năng | JVM | Native |
| --- | --- | --- |
| Repository | Có | Có |
| Projection | Có | Có |
| Auditing | Có | Có |

Bảng này thiếu phiên bản, store, loại projection, ý nghĩa của chữ “Có” và nguồn bằng chứng. Nó chưa đủ để ra quyết định triển khai.

Cách cải thiện:

1. Tạo mô tả môi trường hiện tại và mục tiêu trong tài liệu, ghi dependency đã resolve cùng provider/driver liên quan.
2. Tách repository thành những khả năng đang dùng: query theo `status`, trang có tổng số phần tử, sort được phép và CRUD có ID.
3. Ghi riêng DTO projection và auditing người sửa ở cả hai môi trường.
4. Điền hỗ trợ từ nguồn của đúng release; chỗ chưa rõ giữ `UNKNOWN`.
5. Đặt kiểm chứng của môi trường mục tiêu là `NOT_RUN` cho đến khi có lần chạy tương ứng.
6. Sau khi có kết quả, ghi rõ artifact và tiêu chí của mỗi kết luận.

Nếu native khởi động được nhưng DTO projection thất bại, ghi `FAIL` cho khả năng DTO trên môi trường native. Các khả năng khác giữ trạng thái theo bằng chứng riêng. Nếu luồng auditing chưa chạy vì thiếu môi trường xác thực, ghi `BLOCKED` với điều kiện cụ thể; không đổi thành `PASS` do timestamp đã có giá trị trong một luồng khác.

Kết quả là nhóm biết chính xác điều gì đã có cơ sở, điều gì đã chạy được và điều gì còn cản trở quyết định triển khai.

## 16. Câu hỏi tự kiểm tra

1. Vì sao một interface repository biên dịch được chưa đủ để đánh dấu mọi tính năng là được hỗ trợ?
2. Khi nào nên dùng `UNKNOWN` thay vì `UNSUPPORTED`?
3. Một tính năng có trạng thái `SUPPORTED` và kiểm chứng `FAIL` có mâu thuẫn không?
4. Vì sao phải giữ riêng môi trường JVM và native trong ma trận?
5. Một lần projection thành công chứng minh được những gì và chưa chứng minh được những gì?
6. Khi nâng phiên bản, có được giữ nguyên `PASS` mà không ghi lại môi trường của bằng chứng cũ không?
7. Ma trận tương thích dependency khác ma trận tính năng ở điểm nào?

### Gợi ý trả lời

1. Biên dịch chỉ kiểm tra hợp đồng kiểu; query, mapping, driver và môi trường đích còn cần được xem xét.
2. Khi chưa có đủ căn cứ cho kết luận hỗ trợ hoặc không hỗ trợ trong đúng phạm vi.
3. Không. Một bên là cam kết theo nguồn, bên kia là kết quả của ứng dụng; cần điều tra nguyên nhân thất bại.
4. Hai chế độ có điều kiện thực thi và yêu cầu metadata khác nhau; kết quả không tự chuyển giữa chúng.
5. Nó chứng minh kịch bản cụ thể trên môi trường và artifact đã chạy; không đại diện cho mọi loại projection, store hoặc phiên bản.
6. Không được gán bằng chứng cũ cho môi trường mới. Có thể giữ nó làm lịch sử và ghi rõ tình trạng kiểm chứng lại.
7. Tương thích dependency nói về tổ hợp thành phần; ma trận tính năng nói về hành vi cụ thể và điều kiện hỗ trợ.

## 17. Tiêu chí của một ma trận có thể sử dụng

Một người khác cần đọc được mỗi kết luận theo câu sau:

> Khả năng **X**, trong phạm vi **Y**, trên môi trường **Z**, có mức hỗ trợ **S** dựa vào nguồn **D**; dự án đã có kết quả kiểm chứng **V** với bằng chứng **E** và giới hạn **L**.

Nếu thiếu một thành phần, tài liệu nên nói rõ phần chưa biết. Chính sự phân biệt giữa nguồn hỗ trợ, môi trường và bằng chứng giúp ma trận trở thành công cụ ra quyết định thay vì chỉ là bảng liệt kê tên tính năng.