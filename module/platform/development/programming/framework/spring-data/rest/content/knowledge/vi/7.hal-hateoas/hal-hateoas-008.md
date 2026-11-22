# Biểu diễn tập hợp rỗng, liên kết vắng mặt và quan hệ tùy chọn

Trong Spring Data REST và Spring HATEOAS, một phản hồi HAL có thể mô tả collection, các liên kết điều hướng và những quan hệ giữa tài nguyên. Ba tình huống dễ bị nhầm lẫn là: collection tồn tại nhưng không có phần tử, một link relation không xuất hiện trong phản hồi, và một quan hệ trong mô hình dữ liệu là tùy chọn. Hiểu đúng từng tình huống giúp client xử lý phản hồi chính xác mà không tự suy đoán trạng thái của tài nguyên.

## 1. HAL biểu diễn tài nguyên và liên kết

HAL (Hypertext Application Language) là định dạng JSON dùng để biểu diễn tài nguyên cùng các liên kết liên quan. Hai vùng quan trọng là:

- _links chứa các link relation và địa chỉ href để client điều hướng.
- _embedded chứa tài nguyên được nhúng trực tiếp trong biểu diễn hiện tại.

Ví dụ một collection resource có liên kết tới chính nó và nhúng các sản phẩm:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/products"
    }
  },
  "_embedded": {
    "products": [
      {
        "name": "Keyboard",
        "_links": {
          "self": {
            "href": "/api/products/1"
          }
        }
      }
    ]
  }
}
~~~

Ở đây, products là quan hệ của tập hợp được nhúng. Mỗi phần tử lại có self link riêng. Client có thể đọc dữ liệu nhúng ngay trong phản hồi hoặc theo các liên kết để lấy tài nguyên khác.

Không phải phản hồi nào cũng cần có _embedded. Một tài nguyên có thể chỉ cung cấp liên kết trong _links; client đi theo href để lấy nội dung chi tiết khi cần. Vì vậy, việc không thấy một quan hệ trong _embedded không tự động có nghĩa là quan hệ đó không tồn tại. Hãy kiểm tra cả _links và cấu trúc tài nguyên theo hợp đồng API.

## 2. Collection rỗng vẫn là một tài nguyên hợp lệ

Collection rỗng có nghĩa endpoint collection tồn tại và truy cập được, nhưng hiện tại không có phần tử nào thỏa mãn truy vấn. Ví dụ GET /api/products có thể trả về collection không có sản phẩm.

Một biểu diễn HAL minh họa:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/products"
    }
  },
  "_embedded": {
    "products": []
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Tùy cách tạo representation và cấu hình serializer, quan hệ nhúng rỗng có thể được biểu diễn bằng mảng rỗng hoặc không xuất hiện trong _embedded. Nếu _embedded.products không có mặt, hãy kiểm tra hợp đồng của endpoint và metadata phân trang; đừng tự kết luận rằng endpoint collection không tồn tại.

Khi API trả về PagedModel hoặc representation có thông tin phân trang, totalElements bằng 0 cho biết không có phần tử trong kết quả hiện tại theo truy vấn đó. totalPages cũng có thể bằng 0. Liên kết self vẫn có thể xuất hiện để xác định collection đang được truy cập. Các liên kết next hoặc prev thường không có khi không có trang kế tiếp hoặc trước đó.

Cần phân biệt ba kết quả:

| Tình huống | Ý nghĩa |
|---|---|
| GET collection trả về thành công và số phần tử bằng 0 | Collection tồn tại; kết quả hiện tại rỗng. |
| GET collection trả về thành công và có phần tử | Collection tồn tại; có dữ liệu phù hợp. |
| Không có link relation dẫn tới collection trong một tài nguyên khác | Tài nguyên hiện tại không quảng bá liên kết đó; chưa thể kết luận collection đích rỗng hay không tồn tại. |

Một collection rỗng không phải lỗi. Client thường nên hiển thị trạng thái “chưa có dữ liệu” hoặc “không tìm thấy kết quả phù hợp”, thay vì hiển thị lỗi kết nối.

## 3. Tạo CollectionModel rỗng với Spring HATEOAS

Khi tự xây dựng API bằng Spring HATEOAS, dùng CollectionModel để biểu diễn một tập hợp tài nguyên. CollectionModel vẫn có thể chứa liên kết ngay cả khi danh sách phần tử rỗng.

Ví dụ tạo collection rỗng và giữ self link:

~~~java
CollectionModel<EntityModel<Product>> result = CollectionModel.empty();

result.add(
    linkTo(methodOn(ProductController.class).all())
        .withSelfRel()
);

return result;
~~~

Với collection có dữ liệu, có thể chuyển từng phần tử thành EntityModel và tạo collection model:

~~~java
List<EntityModel<Product>> items = products.stream()
    .map(product -> EntityModel.of(
        product,
        linkTo(methodOn(ProductController.class).one(product.getId()))
            .withSelfRel()
    ))
    .toList();

return CollectionModel.of(
    items,
    linkTo(methodOn(ProductController.class).all()).withSelfRel()
);
~~~

Cả hai nhánh đều trả về cùng kiểu CollectionModel. Client không cần xử lý một kiểu dữ liệu riêng chỉ vì collection đang rỗng. Nếu endpoint cần metadata phân trang, hãy dùng representation phân trang phù hợp và cung cấp tổng số phần tử, số trang cùng các liên kết điều hướng tương ứng.

## 4. Link relation vắng mặt có ý nghĩa gì?

Trong HAL, một link relation chỉ được quảng bá khi nó có mặt trong _links. Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "items": {
      "href": "/api/orders/42/items"
    }
  }
}
~~~

Phản hồi trên có self và items. Nếu không có quan hệ payment, client không thể tìm thấy _links.payment trong tài liệu này.

Liên kết vắng mặt có nghĩa là representation hiện tại không quảng bá quan hệ đó. Nó không tự chứng minh rằng:

- Tài nguyên đích không tồn tại.
- Collection đích đang rỗng.
- Server không có endpoint tương ứng.
- Client bị từ chối quyền truy cập.

Liên kết có thể vắng mặt vì quan hệ không áp dụng cho tài nguyên này, trạng thái nghiệp vụ hiện tại không cho phép hành động, endpoint không được công bố trong representation, hoặc chính sách truy cập không cung cấp liên kết cho client đó. Ý nghĩa chính xác cần được xác định bởi hợp đồng API.

Không nên tạo liên kết giả với href null, chuỗi rỗng hoặc giá trị "null". Nếu quan hệ không được cung cấp, hãy bỏ hẳn link relation khỏi _links. Cách biểu diễn này giúp client phân biệt rõ một liên kết có thể điều hướng với một quan hệ không được quảng bá.

## 5. Quan hệ tùy chọn trong mô hình dữ liệu

Một quan hệ tùy chọn là quan hệ có thể có hoặc không có đối tượng liên kết. Ví dụ, một đơn hàng có thể chưa được gán khách hàng phụ trách; một nhân viên có thể không có quản lý trực tiếp; một bài viết có thể chưa có ảnh đại diện.

Ở tầng Java, quan hệ đơn có thể được biểu diễn bằng Optional hoặc một thuộc tính nullable tùy mô hình và quy ước của dự án. Ví dụ:

~~~java
public class Order {
    private Customer customer;

    public Optional<Customer> getCustomer() {
        return Optional.ofNullable(customer);
    }
}
~~~

Nếu customer có giá trị, API có thể cung cấp liên kết tới tài nguyên khách hàng. Nếu không có, một custom representation có thể bỏ qua relation customer.

Ví dụ xây dựng EntityModel có điều kiện:

~~~java
EntityModel<Order> model = EntityModel.of(order);

model.add(
    linkTo(methodOn(OrderController.class).one(order.getId()))
        .withSelfRel()
);

order.getCustomer().ifPresent(customer ->
    model.add(
        linkTo(methodOn(CustomerController.class).one(customer.getId()))
            .withRel("customer")
    )
);

return model;
~~~

Khi đơn hàng có khách hàng, HAL có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "customer": {
      "href": "/api/customers/7"
    }
  }
}
~~~

Khi không có khách hàng, custom representation ở ví dụ trên chỉ trả về self link. Client kiểm tra sự tồn tại của _links.customer trước khi điều hướng.

Lưu ý: Spring Data REST có thể tự tạo association link dựa trên mapping repository và association, độc lập với việc thuộc tính hiện tại có giá trị hay không. Vì vậy, không nên giả định rằng một association có giá trị null luôn làm link biến mất trong phản hồi được framework tạo tự động. Hãy xem representation thực tế của endpoint và cấu hình công bố association. Nếu hợp đồng yêu cầu chỉ quảng bá link khi quan hệ có đối tượng, hãy tạo representation có điều kiện hoặc tùy chỉnh cách công bố phù hợp.

## 6. Phân biệt link và embedded resource của quan hệ tùy chọn

Một quan hệ có thể được biểu diễn bằng link, bằng dữ liệu nhúng, hoặc bằng cả hai. Hai phần này phục vụ các mục đích khác nhau:

- _links.customer cung cấp địa chỉ để điều hướng tới khách hàng.
- _embedded.customer chứa dữ liệu khách hàng được nhúng trong phản hồi hiện tại.

Ví dụ chỉ có link:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "customer": {
      "href": "/api/customers/7"
    }
  }
}
~~~

Client biết quan hệ customer có thể truy cập nhưng cần gọi href để lấy nội dung khách hàng.

Ví dụ có cả link và embedded resource:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "customer": {
      "href": "/api/customers/7"
    }
  },
  "_embedded": {
    "customer": {
      "name": "An Nguyen",
      "email": "an@example.test",
      "_links": {
        "self": {
          "href": "/api/customers/7"
        }
      }
    }
  }
}
~~~

Nếu không có dữ liệu nhúng, client vẫn có thể theo link nếu link tồn tại. Ngược lại, một representation có thể nhúng dữ liệu mà không cung cấp một link riêng theo hợp đồng cụ thể. Do đó, hãy kiểm tra đúng vị trí dữ liệu mà API cam kết.

## 7. Client nên xử lý các trường hợp này như thế nào?

Client nên đọc quan hệ HAL theo cách an toàn khi thuộc tính có thể vắng mặt. Ví dụ JavaScript:

~~~javascript
const response = await fetch("/api/orders/42");
const order = await response.json();

const customerLink = order._links?.customer;

if (customerLink?.href) {
    const customerResponse = await fetch(customerLink.href);
    const customer = await customerResponse.json();
    renderCustomer(customer);
} else {
    renderNoCustomer();
}
~~~

Đối với collection nhúng, có thể mặc định danh sách về mảng rỗng khi relation không xuất hiện:

~~~javascript
const products = response._embedded?.products ?? [];

if (products.length === 0) {
    renderEmptyState();
} else {
    renderProducts(products);
}
~~~

Đối với collection có phân trang, hãy đọc page metadata nếu endpoint cung cấp:

~~~javascript
const totalElements = response.page?.totalElements ?? products.length;

if (totalElements === 0) {
    renderEmptyState();
}
~~~

Không nên dùng cùng một trạng thái giao diện cho cả “collection rỗng” và “không có link”. Collection rỗng cho biết đã truy cập được collection nhưng không có phần tử; link vắng mặt cho biết representation hiện tại không quảng bá đường dẫn điều hướng. Khi cần biết thêm, client có thể truy cập endpoint gốc hoặc sử dụng một liên kết khác mà API cung cấp.

## 8. Một số quy tắc thiết kế hữu ích

- Trả về collection rỗng khi endpoint collection hợp lệ nhưng truy vấn không có kết quả; không trả về null thay cho danh sách.
- Giữ self link cho tài nguyên hoặc collection để client nhận diện representation hiện tại.
- Chỉ cung cấp link relation khi quan hệ hoặc hành động được quảng bá theo hợp đồng API.
- Với quan hệ tùy chọn, xác định rõ link có luôn tồn tại như một association endpoint hay chỉ xuất hiện khi có đối tượng liên kết.
- Không dùng href null hoặc chuỗi rỗng để biểu diễn link không tồn tại.
- Dùng _embedded cho dữ liệu nhúng và _links cho điều hướng; không suy luận trạng thái quan hệ chỉ từ một trong hai vùng.
- Với collection phân trang, cung cấp metadata nhất quán để client nhận biết kết quả rỗng và điều hướng trang.
- Viết tài liệu cho các quan hệ có điều kiện để client biết khi nào một link có thể xuất hiện.

## 9. Kiểm tra phản hồi HAL

Khi kiểm tra endpoint, hãy thử cả ba trạng thái thay vì chỉ thử trường hợp có dữ liệu:

1. Gọi collection khi có nhiều phần tử và quan sát _embedded, _links cùng metadata phân trang.
2. Gọi cùng collection khi không có phần tử phù hợp; xác nhận phản hồi vẫn là collection hợp lệ và thể hiện tổng số phần tử bằng 0 nếu có page metadata.
3. Đọc một tài nguyên có quan hệ tùy chọn đã được gán và xác nhận link relation hoặc embedded resource theo hợp đồng.
4. Đọc một tài nguyên không có quan hệ tùy chọn và quan sát cách API biểu diễn association.
5. Kiểm tra một relation không được quảng bá trong trạng thái hiện tại; client phải xử lý việc thiếu khóa trong _links.
6. Với Spring Data REST, kiểm tra association link được sinh tự động có luôn xuất hiện hay được điều kiện hóa theo cấu hình và mapping.

Ba khái niệm cần được giữ tách biệt: collection rỗng là kết quả của một tập hợp không có phần tử; link vắng mặt là việc representation không quảng bá một quan hệ điều hướng; quan hệ tùy chọn là trạng thái của mối liên hệ trong mô hình dữ liệu. HAL và Spring HATEOAS cho phép biểu diễn các trạng thái này rõ ràng để client điều hướng và hiển thị phù hợp.
