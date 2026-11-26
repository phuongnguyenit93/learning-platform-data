# SlicedResourcesAssembler và SlicedModel cho Slice theo hỗ trợ

Một màn hình có nút “Xem thêm” thường cần biết còn dữ liệu tiếp theo hay không, nhưng không cần biết toàn bộ tập kết quả có bao nhiêu phần tử hoặc bao nhiêu trang. Nếu repository trả `Slice<T>`, biểu diễn HTTP nên giữ đúng mức thông tin ấy, thay vì tự tạo tổng số để làm response trông giống một `Page<T>`.

Trong chương **Biểu diễn kết quả web** của **Spring Data Commons**, bài học này trình bày cách chuyển kết quả `Slice` thành tài nguyên web có nội dung, metadata và liên kết điều hướng. Ở bộ phiên bản hỗ trợ, `SlicedResourcesAssembler` và mô hình `SlicedModel` phục vụ việc biểu diễn slice trong hệ sinh thái Spring Data Web và Spring HATEOAS. Khả năng truy vấn, projection, cách lấy thêm dữ liệu và cơ chế phân trang thực tế vẫn phụ thuộc module lưu trữ.

## 1. Slice diễn tả điều gì?

`Slice<T>` cung cấp nội dung của một lát kết quả cùng thông tin điều hướng, chẳng hạn:

```java
slice.getContent();
slice.getNumber();
slice.getSize();
slice.getNumberOfElements();
slice.hasNext();
slice.hasPrevious();
slice.isFirst();
slice.isLast();
```

Khác với `Page<T>`, hợp đồng `Slice<T>` không yêu cầu cung cấp `getTotalElements()` hoặc `getTotalPages()`.

| Nhu cầu | Slice | Page |
|---|---|---|
| Nội dung hiện tại | Có | Có |
| Vị trí và kích thước theo Pageable | Có | Có |
| Biết còn lát tiếp theo | Có | Có |
| Tổng số phần tử của tập kết quả | Không thuộc hợp đồng | Có |
| Tổng số trang | Không thuộc hợp đồng | Có |

`Page` mở rộng khả năng của `Slice`. Tuy nhiên, một kết quả chỉ được biết dưới dạng `Slice` không tự có tổng số đáng tin cậy để công khai.

Cần phân biệt `getSize()` và `getNumberOfElements()`: kích thước yêu cầu có thể là 20, trong khi lát cuối chỉ chứa 3 phần tử. Không dùng số phần tử hiện tại làm tổng số của toàn bộ truy vấn.

## 2. Vai trò của assembler và model

Một đường xử lý có thể được tổ chức như sau:

```text
Request với bộ lọc và Pageable
    → service kiểm tra phạm vi nghiệp vụ
    → repository của module trả Slice
    → map từng phần tử sang DTO công khai
    → SlicedResourcesAssembler tạo biểu diễn tài nguyên
    → serializer của media type tạo response HTTP
```

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| Repository | Thực hiện truy vấn có phạm vi và trả kết quả Slice đúng nghĩa |
| Service | Áp dụng quyền, tenant, transaction và chuyển nội dung khi cần |
| Assembler phần tử | Tạo biểu diễn và liên kết của một phần tử |
| `SlicedResourcesAssembler` | Chuyển Slice thành mô hình tài nguyên có điều hướng tương ứng |
| `SlicedModel` | Chứa biểu diễn slice ở tầng web/hypermedia theo thư viện hỗ trợ |
| HTTP serializer | Mã hóa model theo media type và cấu hình đang dùng |

Assembler không tự chạy lại truy vấn để tìm tổng số, không tự xác thực người dùng và không làm một backend chưa có khả năng phân trang trở nên hỗ trợ mọi thao tác trang.

Model cũng không phải repository. Dùng một kiểu model web không thay đổi driver, câu truy vấn hoặc khả năng của derived query.

## 3. Điều kiện hỗ trợ phải được xác định trước

Không nên mặc định mọi phiên bản Spring Data Commons hoặc Spring HATEOAS đều có cùng lớp và overload dành cho slice.

Cần xác định đủ các điều kiện sau trong ứng dụng thực tế:

1. Module persistence hỗ trợ kiểu truy vấn trả `Slice` mà ứng dụng cần.
2. Bộ phiên bản Spring Data Web đang dùng có `SlicedResourcesAssembler` và cơ chế tích hợp tương ứng.
3. Spring HATEOAS cùng hạ tầng web/serialization cần thiết được cấu hình tương thích.
4. Controller sử dụng resolver và assembler thích hợp với stack web đang chạy.
5. Media type và schema response được công bố đúng với model đã chọn.

Các ví dụ assembler bên dưới áp dụng cho **Spring MVC với bộ thư viện có API tương ứng**. Nếu phiên bản chưa cung cấp lớp hoặc hỗ trợ phân giải assembler, không tự tạo import tưởng tượng, ép kiểu từ assembler của `Page`, hoặc chắp vá các phiên bản thư viện không tương thích.

Trong ứng dụng có dependency management, cần nâng cấp theo bộ phiên bản được quản lý. Nếu chưa thể dùng assembler slice, vẫn có thể định nghĩa DTO slice của ứng dụng; phần 11 minh họa cách này mà không cần giả tổng số.

Không suy ra rằng một ví dụ MVC có thể được sao chép nguyên sang WebFlux hoặc một đường truy cập coroutine. Cách đăng ký resolver, kiểu trả về bất đồng bộ và quá trình tạo liên kết cần phù hợp với stack tương ứng.

## 4. Repository phải thực sự trả kết quả Slice

Một hợp đồng repository minh họa:

```java
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

interface ArticleReadRepository extends Repository<Article, Long> {

    Slice<Article> findByStatusAndTenantId(
            ArticleStatus status,
            UUID tenantId,
            Pageable pageable);
}
```

Ví dụ giả định `Article` có `status`, `tenantId` và mapping hợp lệ, còn module lưu trữ hỗ trợ derived query cùng kiểu kết quả này. Các domain type của ứng dụng có thể bao gồm:

```java
enum ArticleStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

record ArticleSummary(Long id, String title) {
}
```

Service có thể đổi nội dung mà vẫn giữ ngữ nghĩa điều hướng:

```java
Slice<Article> articles = repository.findByStatusAndTenantId(
        status,
        verifiedTenantId,
        pageable);

Slice<ArticleSummary> summaries = articles.map(article ->
        new ArticleSummary(article.getId(), article.getTitle()));
```

`verifiedTenantId` phải đến từ cơ chế xác định tenant của ứng dụng. Việc nhận một tenant ID từ request không tự chứng minh quyền truy cập tenant đó.

Đây là minh họa cho cách sử dụng abstraction. Một số module có yêu cầu hoặc hạn chế riêng về phân trang, truy vấn, projection và sắp xếp. Không coi chữ ký trên là bằng chứng mọi module đều thực hiện nó giống nhau.

Nếu dùng projection trả thẳng `ArticleSummary`, cần xác nhận module và kiểu truy vấn hỗ trợ projection đó. Chuyển sang DTO và tạo lớp bao slice là hai quyết định riêng.

## 5. Vì sao Slice có thể tránh nhu cầu đếm tổng?

Một chiến lược phổ biến là yêu cầu tối đa `size + 1` phần tử theo cùng bộ lọc và thứ tự:

```text
Kích thước công khai: 20
Số phần tử thăm dò tối đa: 21

Có 21 phần tử:
    trả 20 phần tử
    hasNext = true

Có tối đa 20 phần tử:
    trả số phần tử đã tìm được
    hasNext = false
```

Đây là một chiến lược thường gặp, không phải mô tả bắt buộc của mọi driver hoặc module. Backend có thể có cơ chế tiếp tục riêng.

Nếu tự triển khai repository fragment theo chiến lược thăm dò, có thể tạo `SliceImpl` từ kết quả đã truy vấn:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;

static <T> Slice<T> fromProbe(List<T> fetched, Pageable pageable) {
    if (pageable.isUnpaged()) {
        throw new IllegalArgumentException("Ví dụ này yêu cầu Pageable có phân trang");
    }

    int size = pageable.getPageSize();
    boolean hasNext = fetched.size() > size;
    int visibleCount = Math.min(fetched.size(), size);

    List<T> visible = new ArrayList<>(fetched.subList(0, visibleCount));
    return new SliceImpl<>(visible, pageable, hasNext);
}
```

Hàm trên chỉ chuyển kết quả thăm dò thành slice. Phần truy vấn trước nó phải thực sự lấy dữ liệu đúng offset/cơ chế tiếp tục, đúng thứ tự và đủ để kết luận `hasNext`; đồng thời cần có giới hạn size phù hợp.

Lấy đúng 20 phần tử rồi đặt `hasNext = true` chỉ vì nhận đủ 20 là suy luận thiếu dữ kiện: có thể đó chính là 20 phần tử cuối cùng. Ngược lại, không được đưa phần tử thăm dò thứ 21 vào `content` nếu hợp đồng công khai size là 20.

## 6. Gắn assembler phần tử

Với hypermedia, mỗi phần tử có thể được bọc bằng `EntityModel` và có liên kết chi tiết riêng:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class ArticleSummaryAssembler implements
        RepresentationModelAssembler<ArticleSummary, EntityModel<ArticleSummary>> {

    @Override
    public EntityModel<ArticleSummary> toModel(ArticleSummary article) {
        return EntityModel.of(
                article,
                Link.of("/api/articles/" + article.id()).withSelfRel());
    }
}
```

Ví dụ giả định ID kiểu `Long` và ứng dụng có endpoint chi tiết tương ứng. Liên kết ở đây là URI tương đối theo thiết kế minh họa. Ứng dụng cần chọn cách xây dựng URI phù hợp nếu có context path, reverse proxy hoặc yêu cầu liên kết tuyệt đối.

Assembler phần tử chỉ tạo biểu diễn. Không nên thêm một truy vấn repository cho từng phần tử chỉ để tạo link từ ID đã có; cách đó có thể làm chi phí tăng theo số phần tử.

Liên kết xuất hiện không thay thế kiểm tra quyền tại endpoint đích. Client vẫn phải được xác thực và kiểm tra phạm vi khi theo liên kết.

## 7. Dùng SlicedResourcesAssembler trong controller

Với API và resolver slice assembler được bộ thư viện hỗ trợ, một controller có thể có dạng:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.SlicedResourcesAssembler;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
class ArticleController {

    private final ArticleQueryService service;
    private final ArticleSummaryAssembler itemAssembler;

    ArticleController(
            ArticleQueryService service,
            ArticleSummaryAssembler itemAssembler) {
        this.service = service;
        this.itemAssembler = itemAssembler;
    }

    @GetMapping(produces = "application/hal+json")
    RepresentationModel<?> list(
            @RequestParam(defaultValue = "PUBLISHED") ArticleStatus status,
            @PageableDefault(
                    size = 20,
                    sort = {"publishedAt", "id"},
                    direction = Sort.Direction.DESC)
            Pageable pageable,
            SlicedResourcesAssembler<ArticleSummary> assembler) {

        Slice<ArticleSummary> slice = service.findVisible(status, pageable);
        return assembler.toModel(slice, itemAssembler);
    }
}
```

`ArticleQueryService.findVisible(...)` là hợp đồng nghiệp vụ của ví dụ: nó xác định tenant/quyền truy cập, gọi repository phù hợp và trả `Slice<ArticleSummary>`. Ví dụ giả định domain có `publishedAt`, `id` và module hỗ trợ thứ tự đã chọn.

`RepresentationModel<?>` là kiểu cha của biểu diễn hypermedia. Kết quả cụ thể được slice assembler tạo theo API của bộ phiên bản hỗ trợ. Khi khai báo trực tiếp kiểu `SlicedModel` trong dự án, cần dùng đúng kiểu và generic mà bộ Spring Data/Spring HATEOAS đó cung cấp.

Dùng kiểu cha ở chữ ký không làm schema tự biến mất: hợp đồng HTTP vẫn là biểu diễn do assembler, model, media type và serializer đang dùng tạo ra.

Khai báo `produces = "application/hal+json"` cần đi cùng hạ tầng HAL được cấu hình. Chỉ viết media type trên annotation không tự cài thư viện hoặc đăng ký mọi module serialization cần thiết.

## 8. SlicedModel giữ ngữ nghĩa điều hướng của slice

Mô hình slice cần diễn đạt được nội dung hiện tại và điều hướng phù hợp mà không giả định có tổng số. Khi dùng hypermedia, client nên đọc các relation liên quan thay vì tự suy ra mọi URL từ cấu trúc nội bộ.

| Relation/khái niệm | Ý nghĩa cần xác định |
|---|---|
| `self` | Tài nguyên kết quả hiện tại, gồm ngữ cảnh truy vấn cần thiết |
| `next` | Lát tiếp theo khi kết quả cho biết còn dữ liệu |
| `prev` | Lát trước khi có điều hướng về trước phù hợp |
| Trang đầu | Có thể biểu diễn nếu model/assembler và backend hỗ trợ |
| Trang cuối | Không tự xác định được chỉ từ một Slice chưa có tổng số |

Một biểu diễn HAL **rút gọn để minh họa relation** có thể trông như:

```json
{
  "_embedded": {
    "articles": [
      {"id": 101, "title": "Bài viết A"},
      {"id": 102, "title": "Bài viết B"}
    ]
  },
  "_links": {
    "self": {
      "href": "/api/articles?status=PUBLISHED&page=0&size=2"
    },
    "next": {
      "href": "/api/articles?status=PUBLISHED&page=1&size=2"
    }
  }
}
```

Ví dụ cố ý chỉ trình bày nội dung và liên kết. Tên relation của collection, metadata slice, các link bổ sung và cấu trúc đầy đủ phải theo model, serializer và cấu hình thực tế; không dùng JSON rút gọn này làm schema bắt buộc cho mọi phiên bản.

Không thêm `totalElements` hoặc `totalPages` chỉ để lấp chỗ trong response. Nếu client cần tổng số chính xác, phải có đường truy vấn và hợp đồng riêng cung cấp thông tin đó, hoặc chọn `Page` khi phù hợp.

## 9. Liên kết phải giữ đúng ngữ cảnh truy vấn

Một URL phân trang không chỉ có `page` và `size`. Nó có thể còn gồm:

```text
status=PUBLISHED
category=engineering
sort=publishedAt,desc
sort=id,desc
```

Nếu `next` làm mất `status` hoặc `category`, client đang chuyển sang tập kết quả khác. Nếu mất một tiêu chí sort, thứ tự có thể thay đổi giữa các lần đọc.

Cần bảo đảm các liên kết giữ đúng bộ lọc, sort, kích thước và quy ước tên tham số mà endpoint sử dụng. Khi cần base link tùy biến, hãy dùng API tạo liên kết mà phiên bản assembler hỗ trợ, thay vì tự nối chuỗi query parameter thiếu kiểm soát.

Các điểm phải chú ý:

- Một query parameter như `sort` có thể xuất hiện nhiều lần; cấu trúc chỉ giữ một giá trị có thể làm mất tiêu chí.
- Nếu request đánh số trang từ 1, liên kết HTTP phải theo đúng quy ước đó, dù số trang nội bộ vẫn bắt đầu từ 0.
- Nếu dùng qualifier cho nhiều nhóm `Pageable`, cần cấu hình assembler/resolver gắn với đúng nhóm; không suy ra `page` luôn là tên cần ghi.
- Reverse proxy hoặc context path có thể ảnh hưởng URI công khai mà client cần theo.
- Base link do ứng dụng truyền vào phải chứa đúng ngữ cảnh truy vấn được công bố.

Không hứa rằng mọi bộ lọc tùy biến đều tự được giữ trong mọi cấu hình. Cần quan sát các liên kết thực tế của endpoint và đối chiếu với hợp đồng API.

## 10. Chuyển Page sang Slice ở tầng web không làm truy vấn nhẹ đi

Vì `Page` cũng là `Slice`, mã sau có thể che giấu một quyết định truy vấn:

```java
Slice<Article> slice = pagingRepository.findAll(pageable);
```

Nếu phương thức `findAll(pageable)` thực tế trả `Page<Article>`, repository vẫn thực hiện đường truy vấn của hợp đồng `Page`. Việc gán kết quả cho biến `Slice` không tự loại bỏ công việc tính tổng đã xảy ra hoặc có thể được thực hiện.

Tương tự, dùng slice assembler để biểu diễn một đối tượng `Page` chỉ thay cách công khai kết quả ở web. Nó không quay ngược lại thay đổi câu truy vấn.

Nếu mục tiêu là tránh nhu cầu đếm tổng, cần chọn phương thức repository hoặc fragment thực sự trả kết quả slice theo khả năng module. Cũng không nên khẳng định mọi `Page` luôn chạy một câu count riêng: module có thể tối ưu trong một số trường hợp. Điều cần kiểm soát là hợp đồng và đường truy cập dữ liệu thực tế.

Mối liên hệ đúng là:

```text
Muốn đổi JSON:
    chọn biểu diễn web thích hợp.

Muốn đổi công việc truy vấn:
    chọn phương thức repository và chiến lược truy cập thích hợp.
```

## 11. Phương án DTO khi chưa có assembler phù hợp

Nếu phiên bản hoặc hạ tầng hiện tại chưa hỗ trợ slice assembler, có thể giữ đúng ngữ nghĩa bằng DTO riêng:

```java
import java.util.List;

import org.springframework.data.domain.Slice;

record SliceResponse<T>(List<T> content, SliceMetadata slice) {

    static <T> SliceResponse<T> from(Slice<T> source) {
        return new SliceResponse<>(
                List.copyOf(source.getContent()),
                new SliceMetadata(
                        source.getNumber(),
                        source.getSize(),
                        source.getNumberOfElements(),
                        source.hasNext(),
                        source.hasPrevious()));
    }
}

record SliceMetadata(
        int number,
        int size,
        int numberOfElements,
        boolean hasNext,
        boolean hasPrevious) {
}
```

Ví dụ dùng Java record và giả định nội dung không chứa phần tử `null` để phù hợp với `List.copyOf`. Nếu hợp đồng nội dung cho phép `null`, cần chọn cách kiểm tra hoặc sao chép thích hợp.

Controller có thể trả:

```java
@GetMapping("/api/articles")
SliceResponse<ArticleSummary> list(Pageable pageable) {
    return SliceResponse.from(service.findVisible(ArticleStatus.PUBLISHED, pageable));
}
```

Đây là một phương án thay thế của endpoint, không đăng ký đồng thời mapping trùng với ví dụ HAL. Response do ứng dụng sở hữu có thể là:

```json
{
  "content": [
    {"id": 101, "title": "Bài viết A"},
    {"id": 102, "title": "Bài viết B"}
  ],
  "slice": {
    "number": 0,
    "size": 2,
    "numberOfElements": 2,
    "hasNext": true,
    "hasPrevious": false
  }
}
```

DTO này không tự có hypermedia link. Nếu hợp đồng cần link, ứng dụng phải tạo chúng đúng ngữ cảnh hoặc dùng hạ tầng hypermedia thích hợp.

Đây cũng không phải JSON mặc định được cam kết của mọi `SlicedModel`. Nó là schema riêng, có tên trường và chính sách do ứng dụng duy trì.

Không dùng `new PageImpl<>(content, pageable, content.size())` để biến slice thành page chỉ vì một assembler cũ yêu cầu `Page`. Độ dài nội dung hiện tại không phải tổng số, nên cách đó tạo metadata và liên kết điều hướng sai.

## 12. Slice không tự là cursor hoặc snapshot

Một `Slice` nhận `Pageable` vẫn có thể dựa trên offset, tùy module. Việc không có tổng số không tự biến nó thành keyset pagination hay cursor pagination.

Giả sử thứ tự là `publishedAt DESC, id DESC`. Khóa `id` phá hòa giúp thứ tự xác định hơn khi nhiều bản ghi có cùng thời điểm, nhưng dữ liệu mới vẫn có thể được thêm vào trước lát đã đọc. Offset của lần sau có thể bị dịch chuyển.

Nếu yêu cầu tránh dịch chuyển hoặc hỗ trợ đọc dữ liệu lớn theo khóa tiếp tục, cần cân nhắc scrolling/cursor theo khả năng module và thiết kế hợp đồng tương ứng. Không tự nhét một cursor vào tham số `page` rồi mong `SlicedResourcesAssembler` hiểu nó.

Tương tự, `hasNext = true` là thông tin của kết quả truy vấn hiện tại. Khi client theo link sau đó, dữ liệu có thể đã thay đổi; không bảo đảm lát tiếp theo vẫn chứa đúng tập phần tử như tại thời điểm trước.

Assembler không cung cấp snapshot hoặc transaction trải qua nhiều request HTTP. Nếu nghiệp vụ cần snapshot, phải có cơ chế đọc và định danh snapshot thích hợp.

## 13. Giữ bộ lọc và quyền trong truy vấn

Một lỗi thường gặp là truy vấn một slice rộng rồi lọc bớt dữ liệu theo quyền trong bộ nhớ:

```java
// Mẫu cần xem lại thiết kế.
var visible = source.getContent().stream()
        .filter(accessPolicy::canRead)
        .toList();
```

Nếu sau đó vẫn giữ nguyên `hasNext` và metadata của `source`, response có thể có ít phần tử, nhiều lát rỗng hoặc điều hướng không phản ánh tập kết quả mà người dùng được phép xem.

Cần đưa điều kiện tenant, trạng thái và quyền vào truy vấn hoặc cơ chế truy cập dữ liệu phù hợp khi có thể. Nếu nghiệp vụ buộc lọc sau truy vấn, phải thiết kế lại chiến lược lấy đủ nội dung và xác định điều hướng; không chỉ thay `content` rồi giữ mọi metadata cũ.

`Slice.map(...)` là phép biến đổi từng phần tử, phù hợp khi một phần tử nguồn tạo một phần tử đích. Nó không thay thế một phép lọc làm thay đổi tập kết quả.

Nếu một link đích yêu cầu quyền riêng, endpoint đích vẫn phải thực thi quyền. Model hypermedia có thể hướng dẫn client, nhưng không phải nguồn thẩm quyền cho phép truy cập.

## 14. Trang rỗng và lát cuối

Cần phân biệt các tình huống:

| Tình huống | Nội dung | Ngữ nghĩa |
|---|---|---|
| Không có dữ liệu trong phạm vi truy vấn | Rỗng | Không có nội dung hiện tại, không tự có tổng số |
| Lát cuối chỉ có vài phần tử | Ít hơn size | Kết quả cho biết không còn lát tiếp theo |
| Lát có đủ size nhưng không còn phần tử thăm dò | Đủ size | Vẫn có thể là lát cuối |
| Client yêu cầu vị trí vượt dữ liệu hiện tại | Có thể rỗng | Không chứng minh toàn bộ tập kết quả luôn rỗng |
| Dữ liệu thay đổi trước khi theo next | Có thể khác dự đoán | Cần giữ chính sách nhất quán đã công bố |

Với hypermedia, collection rỗng có thể cần thông tin kiểu/relation để có hình dạng phù hợp với client. Hãy dùng API xử lý kết quả rỗng mà model/assembler của phiên bản cung cấp, hoặc công bố DTO có danh sách rỗng rõ ràng.

Không mặc định mọi serializer đều xuất cùng một `_embedded` cho collection không có phần tử. Client và schema cần thống nhất cách biểu diễn này.

Cũng không tạo link `next` chỉ vì lát hiện tại có đủ số phần tử bằng size. Nguồn quyết định phải là thông tin điều hướng được truy vấn xác định đúng.

## 15. Tình huống kiểm chứng khi tích hợp

| Trường hợp | Điều cần quan sát |
|---|---|
| Lát đầu còn dữ liệu | Nội dung đúng và có điều hướng tiếp theo phù hợp |
| Lát cuối chưa đủ size | Không tạo next giả |
| Lát cuối đủ size | Không suy ra hasNext chỉ từ độ dài nội dung |
| Kết quả rỗng | Collection và metadata theo hợp đồng |
| Bộ lọc status/category | Link next giữ cùng phạm vi truy vấn |
| Nhiều tiêu chí sort | Giữ đúng thứ tự ưu tiên các tiêu chí |
| Request đánh số trang từ 1 | Link HTTP theo quy ước web đã cấu hình |
| Nhiều Pageable có qualifier | Assembler điều khiển đúng nhóm tham số |
| Reverse proxy/context path | URI công khai có thể được client sử dụng |
| Module không hỗ trợ truy vấn Slice mong muốn | Dùng chiến lược phù hợp, không ép kiểu che lỗi |
| Bộ phiên bản thiếu assembler slice | Dùng DTO hoặc nâng cấp bộ thư viện có chủ đích |
| Repository thực tế trả Page | Không kết luận rằng count đã được loại bỏ |

Kiểm chứng cần xem cả dữ liệu truy vấn lẫn biểu diễn HTTP. JSON hợp lệ về cú pháp không chứng minh `hasNext` đúng, link giữ đủ bộ lọc hoặc repository tránh được công việc đếm tổng.

## 16. Bài tập tự kiểm tra

### Tình huống 1: Có Slice nhưng assembler của dự án chỉ hỗ trợ Page

Nhóm phát triển dự định bọc nội dung vào `PageImpl` với total bằng số phần tử hiện tại.

**Phân tích:** tổng số đó không có căn cứ. Cần dùng assembler slice mà bộ phiên bản hỗ trợ hoặc DTO slice riêng; nếu thật sự cần tổng số, phải truy vấn và công bố nó đúng nghĩa.

### Tình huống 2: Gán Page vào biến Slice để tránh count

Phương thức repository vẫn trả `Page`, nhưng controller chỉ công khai liên kết next.

**Phân tích:** đổi kiểu biến và biểu diễn web không thay đường truy vấn đã thực hiện. Cần chọn phương thức repository thực sự trả slice theo khả năng module nếu mục tiêu là thay đổi công việc truy vấn.

### Tình huống 3: Lấy đúng size phần tử rồi đặt hasNext khi danh sách đầy

Truy vấn trả 20 phần tử và không có thông tin bổ sung.

**Phân tích:** chưa đủ dữ kiện để biết có phần tử thứ 21. Có thể dùng chiến lược thăm dò hoặc cơ chế tiếp tục của backend, tùy module.

### Tình huống 4: Link next làm mất status=PUBLISHED

Client theo next rồi nhận cả bài nháp.

**Phân tích:** điều hướng đã làm thay đổi phạm vi truy vấn. Cần giữ bộ lọc và chính sách quyền ở các request tiếp theo, không chỉ tăng page.

### Tình huống 5: Có next nhưng request sau trả rỗng

Dữ liệu bị xóa giữa hai request.

**Phân tích:** thông tin điều hướng thuộc kết quả trước đó, không phải snapshot tồn tại xuyên request. Cần chấp nhận và xử lý theo hợp đồng nhất quán của ứng dụng.

### Tình huống 6: Annotation HAL đã có nhưng response không đúng model mong muốn

Ứng dụng chưa cấu hình đầy đủ module hypermedia hoặc bộ phiên bản chưa cung cấp API slice tương ứng.

**Phân tích:** media type trên mapping không tự thiết lập toàn bộ hạ tầng. Cần kiểm tra khả năng của bộ thư viện, resolver, model và serializer; DTO riêng là phương án có thể dùng khi chưa có hỗ trợ assembler phù hợp.

Một biểu diễn slice đúng giữ được nội dung, ngữ nghĩa còn dữ liệu và liên kết theo cùng phạm vi truy vấn. Hãy dùng `SlicedResourcesAssembler`/`SlicedModel` khi bộ phiên bản hỗ trợ đầy đủ; khi chưa có, DTO rõ ràng vẫn có thể bảo toàn ngữ nghĩa `Slice` mà không bịa tổng số hoặc thay đổi bản chất truy vấn của module lưu trữ.
