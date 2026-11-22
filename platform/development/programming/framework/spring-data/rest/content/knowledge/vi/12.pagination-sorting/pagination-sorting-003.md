# Metadata phân trang: number, size, totalElements và totalPages

Khi một endpoint Spring Data REST trả về danh sách có phân trang, response thường chứa một khối metadata tên là \`page\`. Bốn trường \`number\`, \`size\`, \`totalElements\` và \`totalPages\` mô tả vị trí trang hiện tại, kích thước trang và quy mô của toàn bộ kết quả truy vấn.

Đọc đúng các trường này giúp client hiển thị bộ điều hướng trang, số lượng bản ghi và trạng thái trang cuối mà không phải tự suy đoán từ số phần tử đang nhìn thấy.

## 1. Metadata nằm ở đâu trong response?

Spring Data REST mặc định sử dụng HAL cho tài nguyên REST. Với một repository resource được phân trang, response có dạng khái quát như sau:

~~~http
GET /people?page=1&size=25
Accept: application/hal+json
~~~

~~~json
{
  "_embedded": {
    "people": [
      { "id": 26, "firstName": "An", "lastName": "Nguyen" },
      { "id": 27, "firstName": "Binh", "lastName": "Tran" }
    ]
  },
  "_links": {
    "first": { "href": "http://localhost:8080/people?page=0&size=25" },
    "prev": { "href": "http://localhost:8080/people?page=0&size=25" },
    "self": { "href": "http://localhost:8080/people?page=1&size=25" },
    "next": { "href": "http://localhost:8080/people?page=2&size=25" },
    "last": { "href": "http://localhost:8080/people?page=3&size=25" }
  },
  "page": {
    "size": 25,
    "totalElements": 82,
    "totalPages": 4,
    "number": 1
  }
}
~~~

Trong response này:

- \`_embedded\` chứa các phần tử của trang hiện tại. Tên relation như \`people\` phụ thuộc tên resource và cấu hình của ứng dụng.
- \`_links\` cung cấp các liên kết điều hướng. Một số link chỉ xuất hiện khi thao tác tương ứng có ý nghĩa.
- \`page\` chứa metadata phân trang.

Ví dụ trên chỉ minh họa cấu trúc. Tên collection relation, URL, các link và số liệu thực tế phụ thuộc endpoint, dữ liệu, cấu hình và phiên bản ứng dụng.

## 2. Ý nghĩa của bốn trường

| Trường | Ý nghĩa | Cách sử dụng ở client |
|---|---|---|
| \`number\` | Số thứ tự của trang hiện tại, bắt đầu từ 0 | Xác định vị trí trang đang xem |
| \`size\` | Kích thước trang đã được áp dụng, tức số phần tử tối đa dự kiến trên một trang | Hiển thị lựa chọn page size và tính phạm vi bản ghi |
| \`totalElements\` | Tổng số phần tử phù hợp với truy vấn trên tất cả các trang | Hiển thị tổng số kết quả |
| \`totalPages\` | Tổng số trang được tính từ tổng phần tử và kích thước trang | Xác định số trang và trạng thái trang cuối |

### number — trang hiện tại, bắt đầu từ 0

\`number\` là chỉ số trang hiện tại theo hệ zero-based.

- Trang đầu tiên có \`number = 0\`.
- Trang thứ hai có \`number = 1\`.
- Trang thứ ba có \`number = 2\`.

Đây là điểm dễ gây lỗi khi giao tiếp giữa API và giao diện. Người dùng thường nhìn thấy trang 1, 2, 3, trong khi API nhận và trả về chỉ số 0, 1, 2.

Ví dụ, nếu giao diện hiển thị số trang theo cách bắt đầu từ 1:

~~~javascript
const displayPageNumber = page.number + 1;
~~~

Khi gửi yêu cầu cho API, dùng chỉ số zero-based mà API yêu cầu. Không gửi trực tiếp số trang hiển thị cho người dùng nếu chưa trừ đi 1.

### size — kích thước trang được áp dụng

\`size\` cho biết số phần tử tối đa mà một trang được phép chứa theo cấu hình phân trang hiện tại. Nó không nhất thiết bằng số phần tử thực tế trong mảng \`_embedded\`.

Ví dụ:

- \`size = 25\` nghĩa là mỗi trang có thể chứa tối đa 25 phần tử.
- Trang đầu và các trang ở giữa thường có 25 phần tử nếu còn đủ dữ liệu.
- Trang cuối có thể chỉ chứa 7 phần tử, nhưng metadata vẫn có \`size = 25\`.

Vì vậy, không dùng độ dài của mảng nội dung để suy ra \`size\`. Đặc biệt, nếu trang cuối có ít phần tử, page size vẫn giữ nguyên.

Client có thể yêu cầu kích thước trang qua query parameter \`size\`, nhưng server có thể áp dụng giá trị mặc định hoặc giới hạn kích thước tối đa. Hãy đọc \`page.size\` trong response để biết kích thước thực tế đã được áp dụng.

### totalElements — tổng số phần tử phù hợp với truy vấn

\`totalElements\` là tổng số bản ghi phù hợp với điều kiện truy vấn trên toàn bộ kết quả, không chỉ số phần tử của trang hiện tại.

Giả sử API trả về trang có 25 phần tử và:

~~~json
{
  "page": {
    "size": 25,
    "totalElements": 82,
    "totalPages": 4,
    "number": 1
  }
}
~~~

Client đang xem trang thứ hai, nhưng tổng số kết quả phù hợp là 82. Con số 25 là giới hạn nội dung của một trang, còn 82 là số lượng trên tất cả các trang.

Nếu request có filter, \`totalElements\` phản ánh số phần tử sau khi áp dụng filter đó. Nó không nhất thiết bằng tổng số bản ghi trong toàn bộ bảng database.

### totalPages — tổng số trang

Khi page size lớn hơn 0, số trang được tính theo công thức:

~~~text
totalPages = ceil(totalElements / size)
~~~

Trong đó \`ceil\` là phép làm tròn lên.

Ví dụ với \`size = 25\`:

| totalElements | totalPages | Diễn giải |
|---:|---:|---|
| 0 | 0 | Không có kết quả |
| 1 | 1 | Một trang có 1 phần tử |
| 25 | 1 | Một trang vừa đủ 25 phần tử |
| 26 | 2 | Trang thứ hai có 1 phần tử |
| 50 | 2 | Hai trang đủ 25 phần tử |
| 82 | 4 | Ba trang đủ 25 phần tử và trang cuối có 7 phần tử |

Với kết quả rỗng và page size hợp lệ lớn hơn 0, \`totalPages\` bằng 0. Không nên tự ép thành 1 để hiển thị trạng thái có trang dữ liệu; giao diện có thể hiển thị “Không có kết quả”.

## 3. Ví dụ tính dữ liệu của từng trang

Giả sử API trả về:

~~~json
{
  "page": {
    "size": 10,
    "totalElements": 23,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Trang hiện tại là trang thứ hai đối với người dùng vì \`number\` bắt đầu từ 0.

Nếu các trang được đánh số liên tục và dữ liệu ổn định, phạm vi vị trí bản ghi của trang này là:

- Vị trí bắt đầu: \`number * size + 1 = 11\`.
- Vị trí kết thúc: \`min((number + 1) * size, totalElements) = 20\`.

Các trang có phạm vi:

| number từ API | Trang hiển thị | Vị trí bản ghi | Số phần tử tối đa |
|---:|---:|---:|---:|
| 0 | 1 | 1–10 | 10 |
| 1 | 2 | 11–20 | 10 |
| 2 | 3 | 21–23 | 10 |

Công thức phạm vi này hữu ích cho giao diện hiển thị “11–20 trên 23 kết quả”. Chỉ tính khi có kết quả và metadata hợp lệ; với trang rỗng hoặc chỉ số trang nằm ngoài phạm vi, nên hiển thị trạng thái rỗng phù hợp thay vì tạo ra phạm vi bản ghi không tồn tại.

## 4. Gửi yêu cầu phân trang và sắp xếp

Spring Data REST thường dùng các query parameter:

- \`page\`: chỉ số trang, bắt đầu từ 0.
- \`size\`: số phần tử tối đa trên một trang.
- \`sort\`: thuộc tính sắp xếp và chiều sắp xếp.

Ví dụ lấy trang thứ hai, mỗi trang 25 phần tử, sắp xếp theo họ tăng dần:

~~~http
GET /people?page=1&size=25&sort=lastName,asc
Accept: application/hal+json
~~~

Có thể truyền nhiều điều kiện sắp xếp bằng cách lặp lại \`sort\`:

~~~http
GET /people?page=0&size=10&sort=lastName,asc&sort=firstName,asc
~~~

Thứ tự sắp xếp ảnh hưởng thứ tự phần tử trong trang. Khi filter hoặc điều kiện truy vấn thay đổi, \`totalElements\` và \`totalPages\` cũng có thể thay đổi. Khi chỉ đổi thứ tự sắp xếp, tổng số kết quả thường không đổi.

Tên query parameter mặc định có thể được cấu hình trong Spring Data REST. Nếu ứng dụng đổi tên tham số, client phải sử dụng tên đã cấu hình thay vì giả định luôn là \`page\`, \`size\` và \`sort\`.

## 5. Dùng các HAL link để điều hướng

Metadata cho biết trạng thái trang; các liên kết HAL cho biết nơi client có thể đi tiếp.

Các relation thường gặp:

- \`first\`: liên kết tới trang đầu.
- \`prev\`: liên kết tới trang trước nếu có.
- \`self\`: liên kết tới tài nguyên/trang hiện tại.
- \`next\`: liên kết tới trang tiếp theo nếu có.
- \`last\`: liên kết tới trang cuối.

Ở trang đầu, thường không có \`prev\`. Ở trang cuối, thường không có \`next\`. Với tập dữ liệu rỗng, các liên kết điều hướng có thể khác với một tập dữ liệu có nhiều trang.

Nên ưu tiên đọc các link do server trả về thay vì tự nối URL hoặc tự tăng giảm query parameter. Link có thể giữ lại filter, sort và những tham số khác mà client cần bảo toàn. Cách làm này cũng giảm phụ thuộc vào cấu trúc URL nội bộ của endpoint.

Ví dụ xử lý theo hướng HAL:

~~~javascript
const page = response.page;
const links = response._links ?? {};

const canGoPrevious = Boolean(links.prev);
const canGoNext = Boolean(links.next);

const currentPageForDisplay = page.number + 1;
const totalPages = page.totalPages;
const totalElements = page.totalElements;
~~~

Khi người dùng chọn trang tiếp theo, client theo \`_links.next.href\` nếu link tồn tại. Không tạo request tiếp theo khi link không được cung cấp.

## 6. Ảnh hưởng của filter, sort và thay đổi dữ liệu

Metadata phản ánh kết quả của request hiện tại. Do đó, client cần làm mới metadata khi các điều kiện truy vấn thay đổi.

**Khi filter thay đổi**

Ví dụ đang tìm tất cả người dùng có trạng thái ACTIVE, sau đó đổi filter sang INACTIVE. \`totalElements\` và \`totalPages\` phải được đọc lại từ response mới. Trang hiện tại có thể không còn hợp lệ đối với tập kết quả mới; thông thường nên quay về trang đầu khi filter thay đổi.

**Khi sort thay đổi**

Thứ tự các phần tử có thể thay đổi, vì vậy client nên gửi request mới và dùng nội dung cùng link từ response mới. Với dữ liệu có thể được cập nhật đồng thời, một phần tử có thể dịch chuyển giữa các trang sau khi sắp xếp lại.

**Khi dữ liệu được thêm hoặc xóa**

\`totalElements\` và \`totalPages\` có thể thay đổi giữa hai request. Nếu một bản ghi bị xóa ở trang cuối, trang cuối có thể không còn đủ dữ liệu hoặc không còn tồn tại. Client nên xử lý response mới và các HAL link thay vì giữ cứng tổng số trang từ response cũ.

**Khi dữ liệu thay đổi trong lúc người dùng chuyển trang**

Phân trang theo offset/page không phải snapshot bất biến. Nếu bản ghi được thêm hoặc xóa trước vị trí offset hiện tại, các phần tử giữa hai lần request có thể bị lặp hoặc bị bỏ qua. Với dữ liệu thay đổi liên tục và yêu cầu duyệt ổn định, cần cân nhắc thiết kế phân trang theo cursor/keyset ở tầng API phù hợp; không thể giải quyết vấn đề này chỉ bằng bốn trường metadata.

## 7. Phân biệt Page với Slice

Trong Spring Data, \`Page<T>\` và \`Slice<T>\` phục vụ hai nhu cầu khác nhau:

- \`Page<T>\` cung cấp thông tin về tổng số phần tử và tổng số trang. Vì vậy, nó phù hợp khi giao diện cần hiển thị tổng kết quả và số trang.
- \`Slice<T>\` tập trung vào việc biết còn dữ liệu ở phía sau hay không, thường thông qua \`hasNext()\`. Nó không yêu cầu biết tổng số phần tử và tổng số trang.

Để cung cấp \`totalElements\` và \`totalPages\`, tầng truy vấn thường cần thông tin đếm tổng số kết quả. Với dữ liệu lớn, truy vấn count có thể tốn chi phí đáng kể. Hãy chọn kiểu kết quả phù hợp với yêu cầu giao diện và hiệu năng; nếu chỉ cần nút “Tải thêm”, không nhất thiết phải truy vấn tổng số trang.

Khả năng biểu diễn cụ thể của endpoint Spring Data REST phụ thuộc kiểu trả về và cấu hình resource. Không giả định mọi collection response đều có đầy đủ bốn trường này.

## 8. Cấu hình kích thước trang

Spring Data REST có kích thước trang mặc định và giới hạn tối đa. Ứng dụng Spring Boot có thể cấu hình các giá trị này trong \`application.yml\`:

~~~yaml
spring:
  data:
    rest:
      default-page-size: 20
      max-page-size: 100
~~~

Trong ví dụ:

- Nếu client không gửi \`size\`, server dùng kích thước mặc định 20.
- Nếu client yêu cầu kích thước lớn hơn giới hạn, server áp dụng giới hạn cấu hình.
- Giá trị \`page.size\` trong response là thông tin cần dùng để hiểu kích thước trang thực tế.

Không nên để client yêu cầu page size quá lớn một cách tùy ý. Trang quá lớn làm tăng dữ liệu truyền qua mạng, bộ nhớ cần thiết để xử lý response và chi phí truy vấn database.

Tên và khả năng cấu hình cụ thể cần được đối chiếu với phiên bản Spring Boot/Spring Data REST mà dự án đang sử dụng.

## 9. Ví dụ xây dựng kiểu dữ liệu phía client

Có thể định nghĩa kiểu metadata để client dùng nhất quán:

~~~typescript
interface PageMetadata {
  number: number;
  size: number;
  totalElements: number;
  totalPages: number;
}
~~~

Ví dụ hàm tạo thông tin hiển thị:

~~~typescript
function getPageSummary(page: PageMetadata) {
  if (page.totalElements === 0) {
    return {
      currentPage: 0,
      totalPages: 0,
      totalElements: 0,
      start: 0,
      end: 0
    };
  }

  const currentPage = page.number + 1;
  const start = page.number * page.size + 1;
  const end = Math.min((page.number + 1) * page.size, page.totalElements);

  return {
    currentPage,
    totalPages: page.totalPages,
    totalElements: page.totalElements,
    start,
    end
  };
}
~~~

Kiểu dữ liệu trên mô tả các trường số trong metadata. Nếu client cần điều hướng theo HAL, hãy đọc thêm \`_links\` và kiểm tra sự tồn tại của từng relation trước khi hiển thị hoặc kích hoạt nút điều hướng.

## 10. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Giao diện hiển thị trang 0 | Dùng trực tiếp \`number\` cho số trang người dùng | Hiển thị \`number + 1\` |
| Trang cuối hiển thị sai page size | Lấy số phần tử thực tế làm \`size\` | Dùng \`page.size\` |
| Tổng kết quả bằng số phần tử của trang hiện tại | Đọc độ dài mảng \`_embedded\` thay cho tổng kết quả | Dùng \`page.totalElements\` |
| Tính thiếu một trang cuối | Dùng phép chia làm tròn xuống | Dùng metadata \`totalPages\` hoặc phép làm tròn lên |
| Không có dữ liệu nhưng vẫn hiển thị trang 1/1 | Ép \`totalPages\` tối thiểu thành 1 | Xử lý riêng trường hợp \`totalElements = 0\` |
| Chuyển trang làm mất filter hoặc sort | Tự tạo URL mới và bỏ query parameter cũ | Theo HAL link server trả về |
| Metadata cũ sau khi đổi filter | Không lấy lại response mới | Gửi request mới và cập nhật cả content lẫn metadata |
| Tổng số trang thay đổi giữa các lần tải | Dữ liệu được thêm/xóa hoặc điều kiện truy vấn thay đổi | Dùng metadata mới nhất, xử lý trang không còn hợp lệ |

## 11. Checklist khi đọc response phân trang

1. Xác nhận endpoint thực sự trả về kết quả phân trang và có khối \`page\`.
2. Đọc \`number\` theo hệ zero-based; cộng 1 khi hiển thị cho người dùng.
3. Dùng \`size\` trong metadata thay vì suy ra từ số phần tử thực tế.
4. Dùng \`totalElements\` để hiển thị tổng số kết quả sau filter.
5. Dùng \`totalPages\` để xác định số trang; xử lý riêng tập dữ liệu rỗng.
6. Dựa vào \`_links.prev\`, \`_links.next\`, \`_links.first\` và \`_links.last\` để điều hướng.
7. Tải lại content và metadata khi filter hoặc sort thay đổi.
8. Không giữ tổng số trang cũ sau khi dữ liệu có thể đã thay đổi.
9. Cân nhắc chi phí truy vấn đếm nếu API không thực sự cần tổng số phần tử.
10. Kiểm thử trang đầu, trang giữa, trang cuối, trang rỗng và yêu cầu page index vượt phạm vi.

Khi hiểu đúng bốn trường metadata, client có thể hiển thị chính xác vị trí trang, kích thước trang, tổng số kết quả và tổng số trang. Kết hợp metadata với HAL links giúp việc điều hướng tuân theo khả năng mà server thực sự cung cấp.
