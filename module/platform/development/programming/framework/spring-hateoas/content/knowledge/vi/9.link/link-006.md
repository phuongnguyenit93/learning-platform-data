# Thuộc tính hreflang của Link trong Spring HATEOAS

Một API có thể cung cấp cùng một tài nguyên bằng nhiều ngôn ngữ. Ví dụ, bài viết có phiên bản tiếng Việt và tiếng Anh; client cần biết liên kết nào dẫn tới phiên bản ngôn ngữ mà người dùng muốn đọc. Spring HATEOAS cho phép gắn metadata `hreflang` vào một `Link` để mô tả ngôn ngữ của tài nguyên ở URI đích.

`hreflang` là một thuộc tính mô tả ngôn ngữ của tài nguyên được liên kết. Nó giúp client nhận biết một liên kết thay thế dẫn tới nội dung bằng ngôn ngữ nào. Thuộc tính này không tự dịch nội dung, không thay thế cơ chế chọn ngôn ngữ của server và cũng không bảo đảm tài nguyên đích thực sự được trả về bằng ngôn ngữ đã khai báo. Server cần tạo URI và representation nhất quán với metadata mà nó công bố.

## 1. hreflang mô tả điều gì?

Trong một hypermedia link, các thuộc tính mô tả những khía cạnh khác nhau của đích liên kết:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `href` | URI của tài nguyên đích. |
| `rel` | Quan hệ giữa tài nguyên hiện tại và tài nguyên đích. |
| `hreflang` | Ngôn ngữ của tài nguyên đích. |
| `type` | Gợi ý media type của tài nguyên đích, ví dụ `application/hal+json`. |
| `title` | Nhãn mô tả liên kết dành cho người dùng hoặc client. |
| `profile` | URI mô tả ngữ nghĩa hoặc cấu trúc bổ sung của tài nguyên đích. |

Ví dụ, một bài viết hiện tại có liên kết `alternate` tới bản tiếng Anh:

```json
{
  "_links": {
    "self": {
      "href": "/articles/42?lang=vi"
    },
    "alternate": {
      "href": "/articles/42?lang=en",
      "hreflang": "en",
      "title": "English version"
    }
  }
}
```

Ở đây, `rel="alternate"` cho biết đây là một biểu diễn thay thế của tài nguyên; `hreflang="en"` cho biết phiên bản đích dùng tiếng Anh. Hai thuộc tính bổ sung cho nhau: relation diễn tả mối quan hệ, còn `hreflang` mô tả ngôn ngữ của đích.

## 2. Giá trị hreflang và mã ngôn ngữ BCP 47

Giá trị `hreflang` thường dùng language tag theo BCP 47. Một số ví dụ phổ biến:

| Language tag | Ngôn ngữ hoặc biến thể |
| --- | --- |
| `vi` | Tiếng Việt. |
| `en` | Tiếng Anh. |
| `en-GB` | Tiếng Anh theo quy ước vùng Vương quốc Anh. |
| `en-US` | Tiếng Anh theo quy ước vùng Hoa Kỳ. |
| `fr-CA` | Tiếng Pháp theo quy ước vùng Canada. |
| `zh-Hant` | Tiếng Trung dùng chữ Phồn thể. |

Language tag có thể bao gồm mã ngôn ngữ, vùng, script hoặc các thành phần phụ khác theo quy tắc BCP 47. Cách viết thường gặp là chữ thường cho language subtag, chữ hoa cho region subtag và dạng viết hoa đầu cho script subtag, ví dụ `en-GB` hoặc `zh-Hant`. Việc so khớp language tag không nên dựa vào khác biệt chữ hoa/chữ thường.

Trong Java, `Locale` có thể chuyển thành language tag bằng `toLanguageTag()`:

```java
Locale locale = Locale.forLanguageTag("fr-CA");
String languageTag = locale.toLanguageTag();
```

Không nên dùng tên ngôn ngữ hiển thị như `English`, `Tiếng Việt` hoặc `Français` làm giá trị `hreflang`. Hãy dùng language tag phù hợp, chẳng hạn `en`, `vi` hoặc `fr`.

Ứng dụng nên xác thực language tag từ cấu hình hoặc dữ liệu đầu vào theo quy ước mà hệ thống hỗ trợ. Không nên mặc định mọi chuỗi do người dùng gửi lên đều là một language tag hợp lệ chỉ vì API `Link` nhận được chuỗi đó.

## 3. Gắn hreflang bằng Link.withHreflang

Spring HATEOAS biểu diễn một liên kết bằng lớp `Link`. Có thể tạo liên kết với `Link.of(...)`, sau đó gọi `withHreflang(...)` để thêm ngôn ngữ của tài nguyên đích:

```java
Link english = Link.of("/articles/42?lang=en", "alternate")
        .withHreflang("en");
```

Để thêm liên kết vào một representation model:

```java
ArticleModel model = new ArticleModel(article.getId(), article.getTitle());

model.add(linkTo(methodOn(ArticleController.class)
        .show(article.getId(), "vi"))
        .withSelfRel());

model.add(Link.of("/articles/" + article.getId() + "?lang=en", "alternate")
        .withHreflang("en"));
```

Ví dụ minh họa model bài viết hiện tại bằng tiếng Việt và một liên kết thay thế bằng tiếng Anh. Trong ứng dụng thực tế, URI nên được tạo từ mapping controller hoặc một link builder phù hợp để tránh ghép chuỗi đường dẫn thủ công. Quan trọng là URI đích phải thực sự chọn đúng phiên bản tiếng Anh.

`withHreflang` tạo một `Link` mang metadata ngôn ngữ. Có thể kiểm tra giá trị này qua `getHreflang()`, thường được trả về dưới dạng `Optional<String>`:

```java
assertThat(english.getHreflang()).contains("en");
```

Nếu link không có `hreflang`, `getHreflang()` không có giá trị. Client và server nên xử lý trường hợp thiếu metadata mà không tự suy luận ngôn ngữ chỉ từ tên relation.

## 4. Nhiều liên kết alternate cho nhiều ngôn ngữ

Một tài nguyên có thể có nhiều phiên bản ngôn ngữ. Khi đó, representation có thể công bố nhiều link cùng relation `alternate`, mỗi link có một `href` và `hreflang` riêng.

```java
model.add(Link.of("/articles/42?lang=vi", "alternate")
        .withHreflang("vi")
        .withTitle("Tiếng Việt"));

model.add(Link.of("/articles/42?lang=en", "alternate")
        .withHreflang("en")
        .withTitle("English"));

model.add(Link.of("/articles/42?lang=fr", "alternate")
        .withHreflang("fr")
        .withTitle("Français"));
```

Trong HAL, nhiều liên kết cùng relation thường được biểu diễn thành một mảng:

```json
{
  "_links": {
    "alternate": [
      {
        "href": "/articles/42?lang=vi",
        "hreflang": "vi",
        "title": "Tiếng Việt"
      },
      {
        "href": "/articles/42?lang=en",
        "hreflang": "en",
        "title": "English"
      },
      {
        "href": "/articles/42?lang=fr",
        "hreflang": "fr",
        "title": "Français"
      }
    ]
  }
}
```

Client có thể duyệt các liên kết `alternate`, so sánh `hreflang` với ngôn ngữ ưu tiên của người dùng rồi chọn URI phù hợp. `title` có thể cung cấp nhãn hiển thị; client không nên dựa vào `title` để xác định language tag vì `hreflang` mới là metadata ngôn ngữ.

Không nên công bố một liên kết thay thế nếu phiên bản tương ứng không tồn tại hoặc người dùng không được phép truy cập. Nếu tài nguyên chỉ có tiếng Việt và tiếng Anh, đừng tạo link `fr` chỉ để danh sách ngôn ngữ trông đầy đủ.

## 5. Kết hợp hreflang với URI do controller tạo

Trong Spring MVC, `WebMvcLinkBuilder` giúp tạo URI dựa trên mapping của controller. Ví dụ controller nhận mã bài viết và tham số ngôn ngữ:

```java
@RestController
@RequestMapping("/articles")
class ArticleController {

    @GetMapping("/{id}")
    ArticleModel show(
            @PathVariable UUID id,
            @RequestParam(defaultValue = "vi") String lang) {
        // Tải nội dung theo id và lang, sau đó tạo model.
    }
}
```

Có thể tạo link cho một ngôn ngữ cụ thể bằng cách truyền tham số tương ứng vào `methodOn`:

```java
Link english = linkTo(methodOn(ArticleController.class)
        .show(articleId, "en"))
        .withRel("alternate")
        .withHreflang("en");
```

`methodOn` cho phép Spring HATEOAS phân tích mapping và các tham số request để dựng URI. Nó không thực thi method controller hay tải nội dung. Khi thay đổi tên query parameter hoặc mapping, link được tạo theo mapping mới.

Hãy bảo đảm cách chọn ngôn ngữ trong controller khớp với link. Nếu `show(id, lang)` bỏ qua tham số `lang` và chỉ dựa vào `Accept-Language`, thì URI có `?lang=en` sẽ không có ý nghĩa nếu server không đọc query parameter đó. Ngược lại, nếu endpoint chọn ngôn ngữ bằng header, hãy thiết kế hợp đồng link và content negotiation phù hợp thay vì công bố một URI gây hiểu nhầm.

## 6. Phân biệt hreflang với Accept-Language và Content-Language

Ba khái niệm này liên quan đến ngôn ngữ nhưng có vai trò khác nhau:

| Thành phần | Nơi xuất hiện | Vai trò |
| --- | --- | --- |
| `hreflang` | Metadata của hypermedia link. | Mô tả ngôn ngữ của tài nguyên tại URI đích. |
| `Accept-Language` | HTTP request header. | Client gửi sở thích ngôn ngữ để server cân nhắc chọn representation. |
| `Content-Language` | HTTP response header. | Server mô tả ngôn ngữ của representation trong response hiện tại. |

Ví dụ client muốn nội dung tiếng Anh có thể gửi:

```http
GET /articles/42 HTTP/1.1
Accept: application/hal+json
Accept-Language: en-GB,en;q=0.9
```

Server có thể trả representation tiếng Anh và header:

```http
Content-Language: en-GB
```

Trong body HAL, một liên kết `alternate` có thể có `hreflang="vi"` để chỉ tới phiên bản tiếng Việt. Như vậy, header `Content-Language` mô tả response hiện tại, còn `hreflang` mô tả đích của một liên kết.

`hreflang` không khiến server tự động chọn ngôn ngữ. Nó cũng không thay thế `Accept-Language`, không thay thế `Content-Language` và không phải cơ chế dịch nội dung. Nếu server thay đổi response theo `Accept-Language`, cần xem xét chính sách cache và header `Vary: Accept-Language` khi phù hợp.

## 7. hreflang trong HAL và khả năng tương thích client

HAL cho phép metadata của link được biểu diễn cùng `href`. Một client hiểu HAL có thể đọc trường `hreflang` trong từng link. Ví dụ link đơn:

```json
{
  "_links": {
    "alternate": {
      "href": "/articles/42?lang=en",
      "hreflang": "en"
    }
  }
}
```

Nếu relation có nhiều link, client cần xử lý cả trường hợp HAL trả một object và trường hợp trả một mảng object. Đừng giả định `alternate` luôn là một object duy nhất khi API có thể công bố nhiều phiên bản ngôn ngữ.

Không phải client nào cũng sử dụng `hreflang`. Client đơn giản có thể chỉ đọc `href`; client đa ngôn ngữ có thể dùng language tag để lựa chọn. Vì vậy, server cần công bố URI hoạt động độc lập và duy trì ý nghĩa relation ổn định. Metadata giúp client thông minh hơn nhưng không thay thế khả năng truy cập trực tiếp vào tài nguyên đích.

Nếu API hỗ trợ media type khác nhau ngoài HAL, hãy kiểm tra cách serializer biểu diễn metadata link cho từng media type. Không suy luận rằng mọi định dạng hypermedia đều có cấu trúc JSON giống HAL.

## 8. Kiểm tra hreflang trong unit test

Có thể kiểm tra metadata trực tiếp trên `Link` mà không cần gọi HTTP:

```java
@Test
void createsAlternateLinkWithLanguage() {
    Link link = Link.of("/articles/42?lang=en", "alternate")
            .withHreflang("en");

    assertThat(link.getRel().value()).isEqualTo("alternate");
    assertThat(link.getHref()).isEqualTo("/articles/42?lang=en");
    assertThat(link.getHreflang()).contains("en");
}
```

Nếu model có nhiều link `alternate`, kiểm tra đủ các language tag và URI tương ứng:

```java
List<Link> alternates = model.getLinks().stream()
        .filter(link -> link.getRel().value().equals("alternate"))
        .toList();

assertThat(alternates)
        .extracting(link -> link.getHreflang().orElse(""))
        .containsExactlyInAnyOrder("vi", "en", "fr");
```

Ví dụ dùng `Stream.toList()`, có sẵn từ Java 16. Với phiên bản Java cũ hơn, có thể dùng `collect(Collectors.toList())`. Test cũng nên kiểm tra `href` của từng ngôn ngữ để tránh trường hợp metadata đúng nhưng URI lại trỏ đến cùng một phiên bản.

## 9. Kiểm tra serialization HAL bằng MockMvc

Unit test xác nhận `Link` có metadata trong bộ nhớ. Kiểm thử HTTP xác nhận metadata đó được xuất ra trong HAL. Ví dụ:

```java
mockMvc.perform(get("/articles/{id}", articleId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.alternate.href").value(
            "/articles/" + articleId + "?lang=en"))
    .andExpect(jsonPath("$._links.alternate.hreflang").value("en"));
```

Nếu có nhiều link `alternate`, JSONPath cần truy cập đúng phần tử trong mảng hoặc dùng matcher để tìm phần tử theo `hreflang`. Không phụ thuộc thứ tự link nếu thứ tự không thuộc hợp đồng API.

Ngoài metadata, hãy kiểm tra URI đích thực sự trả nội dung theo ngôn ngữ đã khai báo. Ví dụ gọi link tiếng Anh và xác nhận response có `Content-Language: en` hoặc nội dung tiếng Anh theo hợp đồng của ứng dụng. Đây là kiểm thử quan trọng để tránh khai báo `hreflang` không đúng với tài nguyên thực tế.

## 10. Những lỗi thường gặp khi sử dụng hreflang

**Dùng tên ngôn ngữ thay cho language tag.** Giá trị `English` hoặc `Tiếng Việt` không phải cách khai báo phù hợp. Dùng `en` hoặc `vi`.

**Gắn hreflang cho ngôn ngữ của response hiện tại.** `hreflang` mô tả ngôn ngữ của tài nguyên đích trong link. Ngôn ngữ của response hiện tại có thể được mô tả bằng `Content-Language`.

**Nghĩ rằng hreflang tự chọn ngôn ngữ.** Thuộc tính này chỉ cung cấp metadata. URI hoặc cơ chế content negotiation vẫn phải xác định cách server trả đúng phiên bản.

**Khai báo sai ngôn ngữ của đích.** Nếu link ghi `en` nhưng endpoint trả tiếng Việt, client có thể lựa chọn sai phiên bản. Hãy kiểm thử đích link.

**Dùng cùng một URI cho mọi phiên bản mà không có quy tắc lựa chọn.** Nếu URI không phân biệt ngôn ngữ và server không dùng header để chọn representation, các link alternate không giúp client đến đúng phiên bản.

**Giả định chỉ có một link alternate.** Một tài nguyên có thể có nhiều phiên bản. Client cần xử lý cả object đơn và mảng link theo cấu trúc HAL.

**Không xác thực language tag.** Dữ liệu cấu hình sai hoặc tag không được hệ thống hỗ trợ có thể làm client hiểu sai. Hãy giới hạn ngôn ngữ được công bố theo những phiên bản thực sự có.

## 11. Hướng dẫn thiết kế API đa ngôn ngữ

Khi công bố nhiều phiên bản ngôn ngữ, nên thống nhất một quy tắc chọn ngôn ngữ cho toàn API. Một số lựa chọn thường gặp:

- Dùng query parameter như `?lang=vi` hoặc `?lang=en` khi muốn URI thể hiện rõ phiên bản.
- Dùng path segment như `/vi/articles/42` hoặc `/en/articles/42` khi ngôn ngữ là một phần ổn định của định danh URI.
- Dùng `Accept-Language` khi server chọn representation theo sở thích của client và URI không cần thay đổi.

Mỗi cách có tác động khác nhau đến cache và khả năng chia sẻ URI. Nếu cùng một URI trả nhiều representation theo header, cần cấu hình cache đúng với tiêu chí lựa chọn. Nếu ngôn ngữ nằm trong URI, các phiên bản có URI riêng và dễ liên kết trực tiếp hơn.

Chỉ công bố relation `alternate` cùng `hreflang` cho các phiên bản mà API thực sự hỗ trợ. Giữ relation ổn định, dùng language tag chuẩn và đảm bảo URI đích tuân theo chính sách ngôn ngữ đã mô tả.

## 12. Bài tập thực hành và tiêu chí hoàn thành

Hãy mở rộng API bài viết để hỗ trợ tiếng Việt và tiếng Anh:

1. Tạo model bài viết có liên kết `self` tới phiên bản hiện tại.
2. Thêm hai link `alternate`, một link có `hreflang="vi"`, một link có `hreflang="en"`.
3. Tạo URI đích sao cho mỗi link thực sự trả đúng phiên bản ngôn ngữ.
4. Thêm `title` cho từng link để giao diện có thể hiển thị nhãn ngôn ngữ.
5. Kiểm tra `Link.getHreflang()` trong unit test.
6. Kiểm tra HAL JSON chứa đúng `href`, `rel` và `hreflang`.
7. Gọi từng URI đích và xác nhận nội dung hoặc `Content-Language` khớp với tag đã công bố.
8. Thử gửi `Accept-Language` khác với ngôn ngữ trong URI và xác định quy tắc ưu tiên của API.

Bạn đã hiểu `hreflang` khi có thể giải thích ngôn ngữ của tài nguyên đích, tạo `Link` bằng `withHreflang`, công bố nhiều liên kết `alternate`, phân biệt metadata link với header HTTP và kiểm thử cả metadata lẫn nội dung thực tế tại URI đích. Điều đó giúp client khám phá đúng phiên bản ngôn ngữ trong một API hypermedia đa ngôn ngữ.
