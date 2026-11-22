# Đọc HAL từ ứng dụng JavaScript và xử lý _embedded, _links

Spring Data REST thường trả representation theo HAL (Hypertext Application Language). Một response HAL chứa dữ liệu tài nguyên, các tài nguyên liên quan được nhúng trong _embedded và các liên kết điều hướng trong _links.

Ứng dụng JavaScript có thể dùng fetch() để đọc JSON HAL. Khi xử lý response, hãy lấy collection từ _embedded theo relation name và theo các URL trong _links để mở tài nguyên, tìm trang tiếp theo hoặc khám phá chức năng API. Cách làm này giúp client thích ứng tốt hơn khi server thay đổi đường dẫn hoặc cấu hình phân trang.

## 1. HAL representation gồm những gì?

Một tài nguyên đơn lẻ có thể có dữ liệu và các liên kết:

~~~json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 120.00,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    },
    "products": {
      "href": "http://localhost:8080/api/products"
    }
  }
}
~~~

Trong representation này:

- Các thuộc tính id, name và price là dữ liệu của tài nguyên.
- _links chứa các quan hệ liên kết (link relations).
- self trỏ tới tài nguyên hiện tại.
- products trỏ tới collection resource.

Một collection response có thể chứa các item trong _embedded:

~~~json
{
  "_embedded": {
    "products": [
      {
        "id": 42,
        "name": "Mechanical Keyboard",
        "price": 120.00,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/products/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products"
    },
    "next": {
      "href": "http://localhost:8080/api/products?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 45,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Ở đây, products là relation name của collection; _embedded.products chứa các item. _links.next trỏ tới trang kế tiếp và page chứa metadata phân trang.

Tên relation trong _embedded phụ thuộc repository rel hoặc cấu hình của API. Không nên mặc định mọi collection đều có key products; hãy đọc đúng rel mà server công bố.

## 2. Yêu cầu HAL từ JavaScript bằng fetch

Khi gọi Spring Data REST, gửi Accept header phù hợp để yêu cầu HAL JSON:

~~~javascript
async function getHal(url) {
    const response = await fetch(url, {
        headers: {
            Accept: "application/hal+json"
        }
    });

    if (!response.ok) {
        throw new Error("HAL request failed: " + response.status);
    }

    return response.json();
}
~~~

Hàm getHal thực hiện các bước:

1. Gửi HTTP GET tới URL được truyền vào.
2. Yêu cầu response theo media type application/hal+json.
3. Kiểm tra status code; nếu response không thành công, ném lỗi.
4. Chuyển response body thành JavaScript object bằng response.json().

Nếu API yêu cầu session cookie, cấu hình credentials phù hợp, ví dụ credentials: "include", và cấu hình CORS/credential ở server đúng với origin của ứng dụng. Nếu API dùng bearer token, thêm Authorization header từ cơ chế quản lý token của ứng dụng; không hardcode hoặc ghi token vào console.

Không nên giả định mọi response đều là JSON HAL. Với endpoint trả 204 No Content hoặc lỗi có body khác định dạng, hãy xử lý theo status và Content-Type trước khi gọi response.json().

## 3. Khám phá collection từ API root

Spring Data REST thường cung cấp một API root có các liên kết tới repository resources. Thay vì tự ghép đường dẫn collection, client có thể đọc link relation từ root:

~~~javascript
const apiRoot = await getHal("/api");

const productsLink = apiRoot._links?.products;

if (!productsLink) {
    throw new Error("Products collection link was not published");
}

const productsCollection = await getHal(productsLink.href);
~~~

Ví dụ này giả định API root nằm tại /api và repository rel là products. Trong ứng dụng khác, base path hoặc rel có thể khác.

Cách khám phá này có lợi ích:

- Client chỉ cần biết entry point của API.
- Server có thể thay đổi URL collection mà không cần client sửa chuỗi endpoint.
- Client có thể khám phá các repository resource được công bố.
- Quan hệ giữa tài nguyên được thể hiện bằng link thay vì quy ước URL riêng trong mã JavaScript.

Nếu API root không có link products, kiểm tra repository có được export hay không, rel có được tùy chỉnh không và client có đang gọi đúng base path không.

## 4. Đọc danh sách từ _embedded

Sau khi tải collection response, lấy item theo relation name:

~~~javascript
const page = await getHal(productsLink.href);

const products = page._embedded?.products ?? [];

for (const product of products) {
    console.log(product.id, product.name, product.price);
}
~~~

Optional chaining (?.) tránh lỗi khi _embedded hoặc products không tồn tại. Toán tử ?? dùng mảng rỗng nếu collection không có phần tử nhúng.

Collection rỗng có thể không có _embedded hoặc không có relation tương ứng. Vì vậy, client không nên truy cập trực tiếp page._embedded.products mà không kiểm tra sự tồn tại.

Mỗi item trong collection có thể mang _links riêng:

~~~javascript
for (const product of products) {
    const selfUrl = product._links?.self?.href;

    if (selfUrl) {
        console.log("Product resource:", selfUrl);
    }
}
~~~

Nếu cần mở chi tiết sản phẩm, dùng self link của item:

~~~javascript
const firstProduct = products[0];

if (firstProduct?._links?.self?.href) {
    const productDetail = await getHal(
        firstProduct._links.self.href
    );

    console.log(productDetail);
}
~~~

Client không cần tự tạo URL dạng /api/products/{id}; self link là địa chỉ tài nguyên do server cung cấp. Điều này giúp tránh phụ thuộc vào cách server định dạng ID hoặc route.

## 5. Theo _links để điều hướng giữa các trang

Collection phân trang có thể cung cấp các link như first, prev, self, next và last. Không phải trang nào cũng có đủ các link này: trang đầu thường không có prev, trang cuối thường không có next.

Để tải trang kế tiếp:

~~~javascript
const currentPage = await getHal(productsLink.href);
const nextUrl = currentPage._links?.next?.href;

if (nextUrl) {
    const nextPage = await getHal(nextUrl);
    const nextProducts = nextPage._embedded?.products ?? [];

    console.log("Next page items:", nextProducts);
}
~~~

Nên dùng href của next thay vì tự tăng tham số page. Link do server cung cấp có thể giữ các tham số filter, sort, size hoặc query khác của request hiện tại.

Tương tự, có thể quay lại trang trước:

~~~javascript
const previousUrl = currentPage._links?.prev?.href;

if (previousUrl) {
    const previousPage = await getHal(previousUrl);
}
~~~

Nếu client cần hiển thị phân trang, đọc metadata từ page:

~~~javascript
const metadata = currentPage.page;

if (metadata) {
    console.log(
        "Page", metadata.number + 1,
        "of", metadata.totalPages,
        "- total items:", metadata.totalElements
    );
}
~~~

number trong HAL page metadata bắt đầu từ 0; khi hiển thị cho người dùng, thường cộng 1 để đánh số trang bắt đầu từ 1.

## 6. Tải tuần tự nhiều trang khi thật sự cần

Một số tác vụ cần đọc toàn bộ collection, chẳng hạn xuất dữ liệu hoặc đồng bộ. Có thể đi theo link next cho tới khi hết trang:

~~~javascript
async function readAllProducts(firstPageUrl) {
    const allProducts = [];
    let nextUrl = firstPageUrl;

    while (nextUrl) {
        const page = await getHal(nextUrl);
        const items = page._embedded?.products ?? [];

        allProducts.push(...items);

        nextUrl = page._links?.next?.href ?? null;
    }

    return allProducts;
}
~~~

Hàm trên không tự tạo URL trang tiếp theo. Nó dùng next link trong mỗi response, giữ nguyên query và điều hướng do server định nghĩa.

Không nên tải toàn bộ collection về trình duyệt chỉ để hiển thị danh sách. Với giao diện thông thường, hãy tải một trang, hiển thị item và chỉ tải trang tiếp theo khi người dùng yêu cầu. Nếu dữ liệu rất lớn, giữ toàn bộ kết quả trong bộ nhớ có thể làm tab trình duyệt chậm hoặc hết bộ nhớ.

Khi chạy tác vụ đồng bộ lớn, cân nhắc xử lý từng trang rồi lưu hoặc gửi tiếp từng batch thay vì giữ mọi item trong một mảng.

## 7. Khám phá quan hệ và link trên một item

Một item có thể chứa link tới các tài nguyên liên quan, ví dụ category hoặc owner:

~~~json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    },
    "category": {
      "href": "http://localhost:8080/api/products/42/category"
    }
  }
}
~~~

Client có thể theo relation category:

~~~javascript
const categoryUrl = productDetail._links?.category?.href;

if (categoryUrl) {
    const category = await getHal(categoryUrl);
    console.log(category);
}
~~~

Tên relation thể hiện ý nghĩa của liên kết. Client nên sử dụng relation name đã được công bố trong response và không giả định mọi Product đều có category link.

Một relation có thể chứa một link object hoặc nhiều link object tùy representation và quan hệ. Nếu API trả mảng link cho một relation, hãy xử lý từng phần tử thay vì luôn giả định giá trị là một object duy nhất.

## 8. Xử lý link template

Một số HAL link có thể là URI template và đi kèm thuộc tính templated:

~~~json
{
  "_links": {
    "search": {
      "href": "http://localhost:8080/api/products/search{?name,page,size}",
      "templated": true
    }
  }
}
~~~

Link này chưa phải URL hoàn chỉnh. Nó mô tả các biến có thể truyền vào như name, page và size.

Không nên gọi fetch trực tiếp với chuỗi chứa dấu ngoặc nhọn. Hãy dùng thư viện URI Template tương thích RFC 6570 hoặc một hàm mở rộng template đã được kiểm tra để tạo URL từ các giá trị được cung cấp.

Ví dụ về cách sử dụng ở mức khái niệm:

~~~javascript
const searchLink = apiRoot._links?.search;

if (searchLink?.templated) {
    // Dùng URI-template library để mở rộng href
    // với name, page và size trước khi gọi getHal().
}
~~~

Khi link không có templated=true, href thường có thể được gọi trực tiếp. Hãy kiểm tra metadata thay vì tự suy đoán từ nội dung URL.

## 9. Phân biệt _embedded và _links

Hai phần này có vai trò khác nhau:

| Thành phần | Nội dung | Cách client sử dụng |
|---|---|---|
| _embedded | Tài nguyên hoặc collection được nhúng trong response hiện tại. | Đọc dữ liệu item ngay trong response. |
| _links | Các URL quan hệ tới tài nguyên, collection hoặc hành động khác. | Khám phá, mở tài nguyên hoặc chuyển tới trang khác. |
| page | Metadata của kết quả phân trang. | Hiển thị số trang, tổng số phần tử và kích thước trang. |

Không phải mọi liên kết đều có dữ liệu tương ứng trong _embedded. Một link category có thể chỉ chứa href; client phải gọi URL đó nếu cần representation của category.

Ngược lại, một item trong _embedded thường cũng có thể mang self link để client mở representation độc lập. Embedded giúp giảm request khi dữ liệu liên quan đã có sẵn; link giúp client tiếp tục điều hướng khi cần thêm dữ liệu.

## 10. Xử lý lỗi và kiểm tra response

Một ứng dụng client nên xử lý các trường hợp thường gặp:

- 401 Unauthorized: request chưa có thông tin xác thực hợp lệ.
- 403 Forbidden: người dùng đã xác thực nhưng không được phép truy cập.
- 404 Not Found: tài nguyên hoặc link đích không còn tồn tại.
- 429 Too Many Requests: client gửi quá nhiều request trong một khoảng thời gian.
- 5xx: lỗi phía server hoặc dịch vụ phụ thuộc.

Ví dụ bắt lỗi:

~~~javascript
try {
    const page = await getHal(productsLink.href);
    const products = page._embedded?.products ?? [];
    renderProducts(products);
} catch (error) {
    showError(error.message);
}
~~~

Nếu response trả về status lỗi, không nên mặc định gọi JSON path của HAL. Có thể kiểm tra Content-Type và body lỗi theo hợp đồng API của ứng dụng.

Khi kiểm thử, xác nhận Accept header là application/hal+json, Content-Type response đúng, _embedded có relation mong đợi, _links chứa self và các link phân trang phù hợp. Với collection rỗng, kiểm tra client không lỗi khi _embedded vắng mặt.

## 11. CORS và xác thực trong trình duyệt

Nếu JavaScript chạy từ origin khác với Spring Data REST, trình duyệt áp dụng CORS. Server cần cho phép origin của client, method và header mà request sử dụng, trong đó có Accept và Authorization nếu được dùng.

Với cookie session, fetch có thể cần credentials: "include". Server phải cấu hình Access-Control-Allow-Credentials và origin cụ thể; không dùng wildcard origin cùng credentials.

Với bearer token, thêm Authorization header từ nơi quản lý token an toàn của ứng dụng. Không đưa token vào URL, không lưu token trong log và không hardcode token trong mã nguồn phía trình duyệt.

CORS chỉ kiểm soát trình duyệt có được phép đọc response từ origin khác hay không. Nó không thay thế authentication hoặc authorization ở Spring Security. API vẫn phải xác thực và phân quyền cho từng tài nguyên.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có _embedded | Collection rỗng, sai relation name hoặc response không phải HAL. | Kiểm tra Content-Type, fixture và rel trong response. |
| products là undefined | Repository dùng rel khác hoặc không có item nhúng. | Đọc relation thực tế và dùng optional chaining. |
| Link next không tồn tại | Đang ở trang cuối hoặc collection chỉ có một trang. | Kiểm tra trước khi điều hướng. |
| fetch không đọc được response | CORS, authentication hoặc network error. | Kiểm tra origin, CORS policy, cookie/token và status. |
| URL có dấu ngoặc nhọn | Client gọi URI template chưa mở rộng. | Dùng URI-template library để thay biến. |
| URL tự ghép bị sai | Client hardcode route hoặc bỏ query đang áp dụng. | Theo href trong _links. |
| Client tải toàn bộ dữ liệu và chậm | Tải mọi trang vào một mảng lớn. | Hiển thị từng trang hoặc xử lý theo batch. |
| JSON parse thất bại | Response rỗng, 204 hoặc body không phải JSON. | Kiểm tra status và Content-Type trước khi parse. |

## 13. Quy trình tích hợp client

Khi kết nối ứng dụng JavaScript với Spring Data REST:

1. Gửi GET tới API root và yêu cầu application/hal+json.
2. Đọc relation của collection cần dùng từ _links.
3. Gọi href của collection thay vì tự ghép endpoint.
4. Đọc item từ _embedded theo relation name thực tế.
5. Dùng self link của item để mở tài nguyên chi tiết.
6. Dùng next hoặc prev link để chuyển trang.
7. Đọc page metadata để hiển thị trạng thái phân trang.
8. Kiểm tra templated=true trước khi mở rộng link search.
9. Xử lý collection rỗng, link không có, response lỗi và CORS.
10. Chỉ tải tất cả trang khi use case thực sự cần; ưu tiên hiển thị theo trang cho giao diện.

JavaScript client đọc HAL bằng cách yêu cầu application/hal+json, lấy tài nguyên nhúng từ _embedded và khám phá URL qua _links. Hãy dựa trên relation name và href do server cung cấp, kiểm tra link trước khi gọi và dùng next/prev để điều hướng. Cách tiếp cận này giúp client giảm phụ thuộc vào cấu trúc URL nội bộ, xử lý phân trang nhất quán và thích ứng tốt hơn với API Spring Data REST.
