# Quản lý phân trang, projection và trạng thái dữ liệu trên giao diện với Spring Data REST

## Mục tiêu

Một giao diện sử dụng Spring Data REST phải đồng bộ nhiều trạng thái: collection đang ở trang nào, filter và sort nào đang áp dụng, projection nào được chọn, request đang chạy hay đã hoàn tất, dữ liệu có rỗng hay lỗi và kết quả có còn mới so với server hay không.

Nếu client chỉ giữ page index rồi tự ghép URL, nó dễ làm mất query parameter, dùng sai trang sau khi đổi filter hoặc tiếp tục hiển thị navigation link cũ. Nếu client tự đoán tên projection, nó có thể yêu cầu một representation chưa được server công bố.

Cách triển khai ổn định là xem HAL response như nguồn điều hướng, quản lý query state riêng với data state và cập nhật item, metadata cùng links theo một response nhất quán. Bài này trình bày cách phối hợp pagination, projection, filter/sort, loading/error/empty state, URL trình duyệt và làm mới dữ liệu sau thao tác ghi.

## 1. Mô hình state phía client

Một collection response Spring Data REST thường có ba phần quan trọng:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/api/people?page=1&size=20"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/people"
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 42,
        "displayName": "Ada Lovelace"
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 51,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Nên quản lý riêng các nhóm state:

| State | Nội dung | Mục đích |
|---|---|---|
| Query | Filter, sort, page size, projection. | Xác định truy vấn hiện tại. |
| Navigation | href first/prev/self/next/last. | Điều hướng theo server. |
| Page metadata | number, size, totalElements, totalPages. | Hiển thị vị trí và số lượng. |
| Data | Các item đã nhận. | Render bảng hoặc danh sách. |
| Request | idle, loading, success, empty, error. | Điều khiển spinner và thông báo. |
| Freshness | Thời điểm tải hoặc cờ stale. | Nhận biết dữ liệu cần refresh. |
| Selection | ID item đang chọn. | Giữ tương tác qua các lần render. |

Khi query state thay đổi, data và navigation state cũ có thể không còn hợp lệ. Khi response mới đến, cập nhật item, page metadata và links cùng lúc để UI không rơi vào trạng thái nửa cũ nửa mới.

## 2. Đọc collection HAL và metadata

Ví dụ hàm tải collection:

~~~javascript
async function fetchHal(url, signal) {
  const response = await fetch(url, {
    headers: { Accept: "application/hal+json" },
    signal
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  return response.json();
}
~~~

Sau khi nhận JSON, lấy item từ relation trong _embedded và metadata từ page:

~~~javascript
function readCollectionState(hal, relation) {
  const links = hal._links ?? {};
  const embedded = hal._embedded ?? {};
  const items = embedded[relation] ?? [];
  const page = hal.page ?? {};

  return {
    items,
    page: {
      number: page.number ?? 0,
      size: page.size ?? items.length,
      totalElements: page.totalElements ?? items.length,
      totalPages: page.totalPages ?? 0
    },
    navigation: {
      first: links.first?.href ?? null,
      prev: links.prev?.href ?? null,
      self: links.self?.href ?? null,
      next: links.next?.href ?? null,
      last: links.last?.href ?? null
    }
  };
}
~~~

Tên relation trong _embedded phụ thuộc tên collection mà Spring Data REST công bố. Không mặc định relation luôn là items hoặc tên entity số nhiều theo tiếng Anh. Hãy khám phá relation từ API root/profile hoặc cấu hình repository.

Một số endpoint trả collection không phân trang và không có page metadata. Client cần hỗ trợ trường hợp đó thay vì truy cập trực tiếp hal.page.number.

## 3. Điều hướng bằng href do server cung cấp

Các relation pagination thường gặp:

- first: trang đầu.
- prev: trang ngay trước.
- self: trang hiện tại.
- next: trang kế tiếp.
- last: trang cuối.

UI bật/tắt nút theo sự hiện diện của link:

~~~javascript
const canGoPrevious = navigation.prev !== null;
const canGoNext = navigation.next !== null;
~~~

Khi người dùng bấm Next, gọi href đã nhận:

~~~javascript
async function goToNextPage(state) {
  const href = state.navigation.next;
  if (!href) return null;
  return fetchHal(href);
}
~~~

Không tự tính page + 1 khi response đã có link next. Href có thể giữ sort, filter, page size và query parameter tùy chỉnh. Tự dựng URL dễ làm mất một phần ngữ cảnh.

Tương tự, hãy theo href của first, prev và last. Nếu relation không tồn tại, thao tác tương ứng hiện không khả dụng theo response. Đừng tạo một URL giả để cố điều hướng.

### Hiển thị số trang

API thường dùng page index bắt đầu từ 0, còn UI hiển thị số thứ tự từ 1:

~~~javascript
const displayedPage = page.number + 1;
const displayedTotalPages = page.totalPages;
~~~

Nếu totalPages bằng 0, hiển thị trạng thái không có kết quả thay vì “Trang 1 / 0”. Với response không có page metadata, không render pagination control theo giả định.

## 4. Quản lý filter, sort và page size

Query state có thể gồm:

~~~javascript
const queryState = {
  searchText: "",
  status: "ACTIVE",
  sort: "lastName,asc",
  size: 20,
  projection: "personSummary"
};
~~~

Khi người dùng đổi filter hoặc sort, đây là một truy vấn mới. Client thường quay về page 0 vì trang 2 của tập kết quả cũ có thể không tồn tại hoặc không còn ý nghĩa trong tập mới.

Ví dụ URL search ban đầu:

~~~text
/api/people/search/findByStatus?status=ACTIVE&page=2&size=20&sort=lastName,asc
~~~

Nếu status đổi thành INACTIVE, hãy khởi tạo truy vấn mới với page=0. Có thể dùng URLSearchParams để tạo URL ban đầu:

~~~javascript
function buildInitialSearchUrl(baseUrl, state) {
  const url = new URL(baseUrl, window.location.origin);
  url.searchParams.set("status", state.status);
  url.searchParams.set("page", "0");
  url.searchParams.set("size", String(state.size));
  url.searchParams.set("sort", state.sort);

  if (state.projection) {
    url.searchParams.set("projection", state.projection);
  }

  return url.toString();
}
~~~

Đây là URL khởi tạo truy vấn. Sau response đầu tiên, dùng href HAL cho các bước pagination. Nếu API dùng search resource, giữ đúng search path và điều kiện query; không quay về collection root rồi vô tình bỏ filter.

## 5. Projection: chọn representation phù hợp với màn hình

Projection cho phép client yêu cầu một view có chọn lọc. Ví dụ:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

Client có thể yêu cầu:

~~~http
GET /api/people?projection=personSummary&page=0&size=20
Accept: application/hal+json
~~~

Giá trị projection phải khớp thuộc tính name trong annotation, không nhất thiết là tên interface. Projection có thể giảm số trường trả về cho màn hình danh sách.

### Projection phải được server công bố

Client không thể tùy ý yêu cầu một interface Java chỉ vì biết tên class. Projection phải được Spring Data REST phát hiện theo package rule hoặc đăng ký tường minh. Client có thể khám phá metadata qua profile/ALPS và sử dụng đúng tên được công bố.

Nếu server không công bố projection tương ứng, request không thể tạo representation mong muốn. Client cần xử lý lỗi hoặc fallback theo hợp đồng API đã định. Không dùng projection như cơ chế authorization: server vẫn phải kiểm soát user có quyền đọc field nào.

### Chọn projection theo màn hình

| Màn hình | Projection gợi ý | Dữ liệu cần |
|---|---|---|
| Danh sách Person | personSummary | Tên và trường nhận diện ngắn. |
| Chi tiết Person | personDetail | Thông tin chi tiết được phép đọc. |
| Danh sách quản trị | personAdminView | Trường quản trị mà user có quyền xem. |
| Chọn Person trong form | personOption | ID, tên hiển thị và giá trị tìm kiếm. |

Không nên dùng một projection quá lớn cho mọi màn hình. Hãy chọn representation theo nhu cầu đọc thực tế, đồng thời bảo đảm quyền đọc ở server.

## 6. Kết hợp pagination và projection

Pagination và projection có thể cùng xuất hiện trong query:

~~~http
GET /api/people?page=0&size=20&sort=lastName,asc&projection=personSummary
Accept: application/hal+json
~~~

Khi điều hướng, href do server trả về nên giữ projection và sort/page size. Client không cần nối thêm projection vào link next nếu server đã đưa tham số đó vào href.

Khi người dùng thay đổi projection, coi đó là một truy vấn mới và thường quay về page 0. Representation có thể thay đổi số trường hoặc association; state trang cũ không nên được giả định vẫn phù hợp.

Lưu projection hiện tại trong query state để UI hiển thị lựa chọn, nhưng sau mỗi response hãy đọc self href và metadata để biết server thực sự đã xử lý truy vấn nào.

## 7. Loading, success, empty và error state

Vòng đời request có thể được biểu diễn:

~~~text
idle
  |
  | user opens page or changes query
  v
loading
  |
  +---- response with items ------> success
  |
  +---- response without items --> empty
  |
  +---- HTTP/network failure ----> error
~~~

Một state mẫu:

~~~javascript
const state = {
  status: "idle",
  items: [],
  page: null,
  navigation: null,
  error: null
};
~~~

Ý nghĩa từng trạng thái:

- Loading: đang chờ response. Có thể disable nút điều hướng để tránh gửi request trùng.
- Success: đã nhận item và metadata hợp lệ.
- Empty: request thành công nhưng không có item phù hợp.
- Error: request thất bại; giữ thông tin đủ để người dùng thử lại hoặc sửa truy vấn.
- Stale: đang hiển thị dữ liệu cũ trong lúc refresh hoặc sau thay đổi có thể ảnh hưởng collection.

Không hiển thị empty state khi request chưa hoàn tất. Nếu khởi tạo items là mảng rỗng rồi render “Không có dữ liệu” trước response, người dùng sẽ thấy thông báo sai trong lúc loading.

## 8. Tránh response cũ ghi đè query mới

Một lỗi phổ biến khi người dùng đổi filter nhanh:

1. Request A tải status ACTIVE.
2. Người dùng đổi sang INACTIVE và request B được gửi.
3. B hoàn thành trước A.
4. A hoàn thành sau và ghi đè UI bằng dữ liệu ACTIVE.

Dùng AbortController để hủy request cũ:

~~~javascript
let activeController;

async function loadQuery(url, onSuccess, onError) {
  activeController?.abort();

  const controller = new AbortController();
  activeController = controller;

  try {
    const hal = await fetchHal(url, controller.signal);
    if (controller.signal.aborted) return;
    onSuccess(hal);
  } catch (error) {
    if (error.name === "AbortError") return;
    onError(error);
  }
}
~~~

Một cách khác là dùng request sequence number và chỉ chấp nhận response nếu request ID vẫn là request mới nhất. Có thể kết hợp cả hai.

Khi query state đổi, xóa hoặc đánh dấu stale các navigation links cũ. Không cho phép người dùng bấm Next từ response cũ trong lúc query mới đang tải.

## 9. Đồng bộ query state với URL trình duyệt

Nếu người dùng refresh hoặc chia sẻ URL, giao diện nên khôi phục được filter, sort, page size và projection cần thiết.

Ví dụ cập nhật query string của trang UI:

~~~javascript
function writeUiStateToUrl(state) {
  const url = new URL(window.location.href);
  url.searchParams.set("status", state.status);
  url.searchParams.set("sort", state.sort);
  url.searchParams.set("size", String(state.size));

  if (state.projection) {
    url.searchParams.set("projection", state.projection);
  } else {
    url.searchParams.delete("projection");
  }

  window.history.replaceState({}, "", url);
}
~~~

Khi ứng dụng khởi động, đọc query string để khôi phục state. Khi người dùng bấm Back/Forward, lắng nghe popstate và tải lại truy vấn tương ứng.

Phân biệt URL của trang UI với href của API. URL UI lưu trạng thái hiển thị; href HAL là URI server công bố để gọi API. Không coi hai URL này là một.

## 10. Selection và trạng thái thao tác trên item

Danh sách có thể giữ selection khi chuyển trang hoặc đổi projection. Cần quyết định rõ selection:

- Chỉ thuộc trang hiện tại.
- Được giữ xuyên các trang.
- Được giữ theo filter hiện tại.
- Bị xóa khi query context thay đổi.

Nếu cho phép chọn nhiều item xuyên trang, lưu ID ổn định thay vì lưu object response đầy đủ. Representation có thể thay đổi khi projection thay đổi hoặc khi server refresh dữ liệu.

~~~javascript
const selectedIds = new Set();

function toggleSelection(id) {
  if (selectedIds.has(id)) {
    selectedIds.delete(id);
  } else {
    selectedIds.add(id);
  }
}
~~~

Khi thực hiện bulk action, server vẫn phải xác minh quyền trên từng ID. Selection trên UI không chứng minh user có quyền thao tác với tất cả item.

## 11. Làm mới dữ liệu sau thao tác ghi

Sau khi tạo, sửa hoặc xóa item, collection hiện tại có thể không còn chính xác:

- Item mới có thể thuộc trang đầu theo sort hiện tại.
- Item vừa sửa có thể không còn thỏa filter.
- Item vừa xóa có thể khiến trang cuối không còn hợp lệ.
- Thay đổi association có thể ảnh hưởng projection hoặc search result.

Có thể cập nhật item từ response của thao tác ghi nếu hợp đồng API trả đủ dữ liệu, sau đó refresh collection bằng href phù hợp. Nếu server trả Location hoặc link mới, dùng URI đó để tải resource.

Sau khi xóa item cuối cùng của trang cuối, có thể cần quay về trang trước hoặc first nếu metadata mới cho biết trang hiện tại không còn hợp lệ. Đọc links và metadata sau refresh thay vì suy đoán từ số item cũ.

### Optimistic update

UI có thể cập nhật tạm thời để phản hồi nhanh, nhưng cần rollback nếu request thất bại. Với thay đổi ảnh hưởng sort/filter/pagination, refresh từ server thường cần thiết để tránh giữ item ở vị trí sai.

Không trình bày optimistic data như thể server đã xác nhận khi request còn pending. Thể hiện trạng thái đang lưu và lỗi nếu server từ chối.

## 12. Dữ liệu thay đổi giữa các lần phân trang

Offset pagination có thể dịch chuyển khi bản ghi được thêm, xóa hoặc đổi sort key giữa các request.

Ví dụ:

1. Client tải trang 0, size 10.
2. Một bản ghi mới được thêm vào đầu danh sách.
3. Client theo link next sang trang 1.
4. Một item có thể lặp lại hoặc bị bỏ qua vì vị trí bản ghi đã dịch chuyển.

HAL links giữ ngữ cảnh truy vấn và vị trí trang tại thời điểm response được tạo, nhưng không bảo đảm snapshot bất biến giữa nhiều request.

Để giảm vấn đề:

- Dùng sort có thứ tự xác định.
- Nếu sort key không duy nhất, thêm khóa duy nhất làm tiêu chí phụ khi API hỗ trợ.
- Refresh collection sau thao tác ghi có ảnh hưởng tới tập kết quả.
- Chấp nhận danh sách có thể thay đổi giữa các lần tải.
- Với dữ liệu thay đổi liên tục hoặc cần duyệt nhất quán, cân nhắc cursor/keyset pagination nếu backend hỗ trợ.

## 13. Cập nhật UI khi API trả lỗi

UI nên phân loại theo HTTP status hoặc error code:

| Lỗi | Hành vi giao diện gợi ý |
|---|---|
| 400 Bad Request | Hiển thị lỗi input/filter và giữ query để sửa. |
| 401 Unauthorized | Yêu cầu đăng nhập hoặc làm mới phiên. |
| 403 Forbidden | Thông báo không có quyền; ẩn hoặc disable thao tác phù hợp. |
| 404 Not Found | Resource có thể đã bị xóa; refresh collection hoặc quay về danh sách. |
| 409 Conflict | Thông báo dữ liệu đã thay đổi hoặc workflow không còn phù hợp; tải lại resource. |
| 429 Too Many Requests | Giảm tần suất request và tuân thủ Retry-After nếu server gửi. |
| 5xx | Thông báo lỗi hệ thống và cho phép thử lại có kiểm soát. |

Nếu response dùng Problem Details, client có thể đọc title, detail, status và extension code. Ưu tiên machine-readable code cho logic UI; không so sánh message đã dịch để quyết định hành vi.

## 14. Ví dụ state reducer

Đoạn mã sau minh họa state container đơn giản cho collection:

~~~javascript
const initialState = {
  status: "idle",
  items: [],
  page: null,
  navigation: null,
  error: null
};

function reducer(state, action) {
  switch (action.type) {
    case "LOAD_START":
      return {
        ...state,
        status: "loading",
        error: null
      };

    case "LOAD_SUCCESS":
      return {
        status: action.items.length ? "success" : "empty",
        items: action.items,
        page: action.page,
        navigation: action.navigation,
        error: null
      };

    case "LOAD_ERROR":
      return {
        ...state,
        status: "error",
        error: action.error
      };

    case "CLEAR":
      return initialState;

    default:
      return state;
  }
}
~~~

Khi tải response, dispatch một action duy nhất mang item, page metadata và navigation links. Nhờ đó, UI không rơi vào trạng thái item đã đổi nhưng nút Next vẫn trỏ tới query trước.

Nếu cần giữ item cũ trong lúc refresh, thêm cờ isRefreshing và đánh dấu stale. Không dùng status success để che việc request mới vẫn đang chạy.

## 15. Quy trình triển khai

1. Khám phá collection relation và search resource từ API root/profile.
2. Xác định relation trong _embedded và cấu trúc page metadata thực tế.
3. Khám phá projection được công bố và chọn đúng tên annotation hoặc ALPS.
4. Tách query state khỏi data, navigation và request state.
5. Tạo URL khởi tạo cho filter, sort, page size và projection.
6. Sau response, lưu href first/prev/self/next/last và theo href khi điều hướng.
7. Khi filter, sort, size hoặc projection đổi, bắt đầu truy vấn mới và thường quay về page 0.
8. Hủy hoặc bỏ qua response cũ để tránh race condition.
9. Đồng bộ query state với URL UI nếu cần refresh và Back/Forward.
10. Cập nhật selection theo chính sách rõ ràng.
11. Refresh collection sau thao tác ghi có thể thay đổi membership, order hoặc page count.
12. Xử lý loading, empty, error, stale và conflict riêng biệt.
13. Kiểm thử bằng HAL response thực tế của phiên bản Spring Data REST đang dùng.

## 16. Những lỗi thường gặp

1. **Tự tính next page và ghép URL.** Có thể làm mất sort, filter, projection hoặc query parameter.
2. **Giả định tên relation embedded luôn cố định.** Đọc relation thực tế do server công bố.
3. **Giả định mọi response đều có page metadata.** Endpoint không phân trang có thể không có object page.
4. **Nhầm page index với số trang UI.** API thường bắt đầu từ 0, UI thường hiển thị từ 1.
5. **Đổi filter nhưng giữ page index cũ.** Tập kết quả mới có thể ít trang hơn; bắt đầu lại từ trang đầu.
6. **Dùng tên interface thay cho projection name.** Client phải gửi giá trị annotation name.
7. **Giả định projection có thể được yêu cầu tùy ý.** Server phải phát hiện hoặc đăng ký projection.
8. **Dùng projection làm authorization.** Projection không thay thế quyền đọc dữ liệu.
9. **Hiển thị empty state khi request vẫn loading.** Chỉ kết luận empty sau response thành công.
10. **Response cũ ghi đè query mới.** Dùng AbortController hoặc request sequence.
11. **Giữ navigation links cũ khi query đổi.** Xóa hoặc đánh dấu stale links trước khi tải mới.
12. **Không refresh sau thao tác ghi.** Item có thể đổi vị trí, rời filter hoặc làm page count thay đổi.
13. **Giữ selection bằng object cũ.** Dùng ID ổn định và kiểm tra quyền ở server.
14. **Coi optimistic update là dữ liệu đã lưu.** Phải rollback khi server từ chối.
15. **Giả định pagination là snapshot.** Offset pagination có thể lặp hoặc bỏ sót item khi dữ liệu thay đổi.
16. **Xử lý mọi HTTP error bằng một message.** Phân loại 401, 403, 404, 409, 429 và 5xx.
17. **Dùng message text để điều khiển UI.** Dùng error code ổn định.
18. **Không kiểm tra URL sau refresh hoặc Back/Forward.** Khôi phục query state từ URL UI và tải lại API đúng ngữ cảnh.

## 17. Checklist triển khai

- Đã đọc đúng collection relation và _embedded key.
- Đã đọc page metadata và xử lý response không có pagination.
- Đã lưu các navigation href từ _links.
- Đã dùng href server cung cấp cho first/prev/next/last.
- Đã giữ filter, sort, size và projection khi phân trang.
- Đã reset về trang đầu khi query context thay đổi.
- Đã chọn projection name được server công bố.
- Đã không dùng projection thay cho authorization.
- Đã tách query, navigation, data và request state.
- Đã xử lý loading, empty, error và stale riêng biệt.
- Đã ngăn response cũ ghi đè query mới.
- Đã quyết định selection có tồn tại qua trang hay filter không.
- Đã refresh collection sau thao tác ghi có ảnh hưởng kết quả.
- Đã xử lý conflict và dữ liệu thay đổi giữa các request.
- Đã đồng bộ URL UI nếu cần refresh hoặc Back/Forward.
- Đã kiểm thử API response và trạng thái UI theo các tình huống biên.

## Tóm tắt

Một client Spring Data REST nên quản lý pagination, projection và UI state như những phần liên quan nhưng độc lập. Page metadata cho biết vị trí và số lượng; HAL links cho biết hướng điều hướng; projection xác định representation được yêu cầu; query state giữ filter, sort, page size và projection hiện tại.

Hãy theo href do server trả về, reset page khi query context thay đổi, ngăn response cũ ghi đè dữ liệu mới và thể hiện loading/empty/error/stale rõ ràng. Sau thao tác ghi, refresh collection khi membership, sort hoặc page count có thể thay đổi. Với offset pagination, dữ liệu có thể dịch chuyển giữa các request; metadata và links không tạo snapshot bất biến.

## Tài liệu tham khảo

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring HATEOAS — HAL Support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [MDN — Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)
- [MDN — AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
