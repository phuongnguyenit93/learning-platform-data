# Thiết kế record lồng nhau cho dữ liệu có cấu trúc

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record được chuẩn hóa từ Java 16 và tiếp tục là công cụ phù hợp trong Java hiện đại. Bài học này hướng dẫn cách tổ chức dữ liệu nhiều tầng bằng record lồng nhau, từ DTO và phản hồi API đến cây dữ liệu và projection, đồng thời giữ rõ ranh giới giữa cấu trúc dữ liệu, bất biến và hợp đồng công khai.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt **record lồng nhau** (nested record declaration) với **record chứa một record khác** (composition).
- Chọn vị trí khai báo kiểu con: record lồng trong record, kiểu top-level hay local record trong phương thức.
- Xây dựng cấu trúc dữ liệu nhiều tầng mà mỗi tầng tự bảo vệ bất biến của nó.
- Thiết kế danh sách và cây record, xử lý collection mutable và tránh cấu trúc quá sâu.
- Hiểu cách cấu trúc record ảnh hưởng đến JSON/API, khả năng tái sử dụng và tương thích khi thay đổi hợp đồng.

## 1. Hai khái niệm cần phân biệt

Cụm từ “record lồng nhau” có thể chỉ hai điều khác nhau:

1. **Lồng khai báo kiểu:** khai báo một record bên trong thân của class hoặc record khác để đặt tên kiểu trong phạm vi của kiểu bao ngoài.
2. **Lồng dữ liệu:** một component của record có kiểu là record khác, hoặc là collection chứa các record đó. Đây là quan hệ thành phần (*composition*).

Hai cách này thường được dùng cùng nhau, nhưng không bắt buộc.

Ví dụ:

```java
record Address(String city, String postalCode) {}

record Customer(String id, Address address) {}
```

`Address` và `Customer` là hai record top-level riêng biệt; dữ liệu của `Customer` vẫn được lồng theo cấu trúc vì component `address` có kiểu `Address`.

Nếu `Address` chỉ thuộc về `Customer` và không có ý nghĩa độc lập ở nơi khác, ta có thể khai báo nó bên trong:

```java
public record Customer(String id, Customer.Address address) {
    public record Address(String city, String postalCode) {}
}
```

Lúc này tên kiểu đầy đủ là `Customer.Address`. Cả hai ví dụ đều dùng composition; chỉ ví dụ thứ hai mới có nested record declaration.

**Quyết định đầu tiên:** kiểu con có phải khái niệm dùng chung trong nhiều phần của ứng dụng không? Nếu có, record top-level thường dễ tái sử dụng. Nếu kiểu con chỉ là một phần của hợp đồng kiểu bao ngoài, nested record giúp gom nhóm và tránh làm rộng namespace.

## 2. Quy tắc của nested record trong Java

Một member record khai báo trong class hoặc record khác **được ngầm định là static**. Không cần ghi từ khóa `static` trong khai báo. Điều đó có một số hệ quả quan trọng:

- Có thể tạo instance bằng tên kiểu bao ngoài, ví dụ `new Customer.Address(...)`; không cần tạo instance `Customer` trước.
- Nested record không giữ tham chiếu ngầm tới instance của kiểu bao ngoài.
- Nested record không thể truy cập trực tiếp các trường instance của đối tượng bao ngoài; nó chỉ dùng dữ liệu được truyền qua component hoặc tham số.
- Nested record có thể truy cập thành viên `static` của kiểu bao ngoài theo quy tắc truy cập Java, kể cả thành viên `private` khi được phép.
- Nested record có thể có component, constructor, phương thức và nested type riêng như một record thông thường.

Ví dụ:

```java
public record CustomerProfile(String customerId, CustomerProfile.Address address) {
    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.strip();
    }

    public record Address(String city, String postalCode) {
        public Address {
            city = CustomerProfile.requireText(city, "city");
            postalCode = CustomerProfile.requireText(postalCode, "postalCode");
        }
    }
}
```

Cách khởi tạo:

```java
CustomerProfile.Address address =
        new CustomerProfile.Address("Ho Chi Minh City", "700000");

CustomerProfile profile =
        new CustomerProfile("CUS-100", address);
```

`Address` không cần một `CustomerProfile` để tồn tại. Đây là đặc điểm của nested record ngầm định static, khác với một inner class thông thường có thể gắn với instance bên ngoài.

### 2.1. Nested record trong generic class

Vì nested record là static, nó không thể tự sử dụng tham số kiểu của instance bao ngoài. Ví dụ sau **không hợp lệ**:

```java
class Box<T> {
    // Không hợp lệ: nested record là static và không thể dùng T của Box<T>.
    // record Snapshot(T value) {}
}
```

Nếu kiểu con cần generic, hãy khai báo tham số kiểu riêng cho record:

```java
class Box<T> {
    record Snapshot<U>(U value) {}

    Snapshot<T> snapshot(T value) {
        return new Snapshot<>(value);
    }
}
```

`Snapshot` có tham số kiểu `U` của chính nó. Phương thức instance của `Box<T>` có thể dùng `T` để tạo `Snapshot<T>`, nhưng bản thân nested record không phụ thuộc vào instance của `Box`.

### 2.2. Local record trong phương thức

Java cũng cho phép khai báo record trong một block hoặc phương thức. Local record có phạm vi sử dụng cục bộ, hữu ích cho kiểu dữ liệu trung gian chỉ phục vụ một phép xử lý.

Ví dụ sau giả sử `CustomerProfile` đã được khai báo như ở phần tiếp theo:

```java
import java.util.List;

public class CustomerReports {
    public static List<String> distinctRegions(
            List<CustomerProfile> customers) {

        record RegionKey(String city, String postalCode) {}

        return customers.stream()
                .map(customer -> new RegionKey(
                        customer.address().city(),
                        customer.address().postalCode()))
                .distinct()
                .map(key -> key.city() + " / " + key.postalCode())
                .toList();
    }
}
```

`RegionKey` chỉ tồn tại trong phạm vi phương thức. Local record cũng được ngầm định static, nên không thể capture biến local hoặc truy cập instance bao ngoài như một local inner class. Dữ liệu cần thiết phải được truyền qua constructor. Trong ví dụ, `distinct()` dùng equality theo cả thành phố và mã bưu chính để giữ lại các cặp khu vực không trùng nhau.

Dùng local record khi kiểu trung gian có nhiều thành phần và cần equality theo giá trị. Nếu chỉ cần một biến hoặc một phép ánh xạ đơn giản, không cần tạo thêm kiểu.

## 3. Thiết kế DTO nhiều tầng

Một API thường trả về một đối tượng tổng hợp gồm thông tin chính, thông tin liên quan và danh sách phần tử. Thay vì dồn tất cả thành phần vào một record phẳng với tên trường dài, hãy mô hình hóa các nhóm dữ liệu có ý nghĩa.

Ví dụ một phản hồi hồ sơ khách hàng:

Đây là phiên bản đầy đủ hơn của `CustomerProfile`, thay thế khai báo ngắn ở phần 2 khi thực hành trong một file riêng:

```java
import java.util.List;
import java.util.Objects;

public record CustomerProfile(
        String customerId,
        CustomerProfile.Address address,
        List<CustomerProfile.Contact> contacts
) {
    public CustomerProfile {
        customerId = requireText(customerId, "customerId");
        Objects.requireNonNull(address, "address");
        contacts = List.copyOf(
                Objects.requireNonNull(contacts, "contacts"));
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field);
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return normalized;
    }

    public record Address(
            String street,
            String city,
            String postalCode
    ) {
        public Address {
            street = requireText(street, "street");
            city = requireText(city, "city");
            postalCode = requireText(postalCode, "postalCode");
        }
    }

    public record Contact(String type, String value) {
        public Contact {
            type = requireText(type, "type");
            value = requireText(value, "value");
        }
    }
}
```

Các kiểu con có thể được tái sử dụng trong phạm vi tên `CustomerProfile`:

```java
CustomerProfile profile = new CustomerProfile(
        "CUS-100",
        new CustomerProfile.Address(
                "12 Nguyen Hue",
                "Ho Chi Minh City",
                "700000"),
        List.of(
                new CustomerProfile.Contact("EMAIL", "customer@example.com"),
                new CustomerProfile.Contact("PHONE", "+84000000000")
        )
);

System.out.println(profile.address().city());
System.out.println(profile.contacts().get(0).value());
```

Cấu trúc JSON tương ứng có dạng:

```json
{
  "customerId": "CUS-100",
  "address": {
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  },
  "contacts": [
    {
      "type": "EMAIL",
      "value": "customer@example.com"
    },
    {
      "type": "PHONE",
      "value": "+84000000000"
    }
  ]
}
```

Mỗi tầng diễn tả một nhóm dữ liệu có tên và trách nhiệm rõ ràng. Người dùng API có thể đọc cấu trúc lồng nhau mà không cần ghi nhớ những tên phẳng như `addressCity`, `addressPostalCode` hay `contact1Value`.

### 3.1. Tách validation theo đúng tầng

Trong ví dụ trên:

- `CustomerProfile` xác thực mã khách hàng, yêu cầu địa chỉ và sao chép danh sách contacts.
- `Address` xác thực các thành phần địa chỉ.
- `Contact` xác thực loại liên hệ và giá trị.

Khi tạo `CustomerProfile`, các constructor của `Address` và `Contact` đã bảo vệ bất biến riêng của chúng. Constructor bên ngoài vẫn phải kiểm tra component bắt buộc và collection. Không nên gom toàn bộ kiểm tra của các record con vào constructor cha, vì cách đó làm kiểu cha hiểu chi tiết nội bộ của từng kiểu con.

`List.copyOf` tạo danh sách không thể thêm/xóa qua tham chiếu được trả ra và không giữ thay đổi từ danh sách nguồn. Tuy nhiên, đây là **bản sao nông**: nếu phần tử là đối tượng mutable, trạng thái bên trong phần tử vẫn có thể đổi. Ví dụ này an toàn hơn vì `Contact` và `Address` chỉ chứa `String` bất biến.

### 3.2. Đừng nhầm dữ liệu lồng nhau với một component tùy ý

Tên component nên phản ánh một khái niệm có ý nghĩa. Ví dụ:

- `address` là một nhóm dữ liệu địa chỉ.
- `contacts` là một tập các phương thức liên hệ.
- `pagination` là thông tin phân trang.
- `items` là danh sách phần tử của kết quả.

Nếu record ngoài chỉ chứa một danh sách các record con và không có thêm ý nghĩa, hãy cân nhắc liệu kiểu bao ngoài có thật sự cần thiết hay có thể trả về collection trực tiếp. Tạo thêm lớp bao chỉ có ích khi nó mang metadata, quy tắc hoặc hợp đồng riêng.

## 4. Mô hình hóa danh sách và cây record

Record có thể lồng nhiều tầng thông qua component là record hoặc collection của record. Điều này phù hợp với cấu trúc phân cấp như danh mục, menu, cây tổ chức, cây phân loại và nội dung tài liệu.

### 4.1. Record đệ quy cho cây dữ liệu

Ví dụ cây danh mục:

```java
import java.util.List;
import java.util.Objects;

public record CategoryNode(
        String code,
        String name,
        List<CategoryNode> children
) {
    public CategoryNode {
        code = requireText(code, "code");
        name = requireText(name, "name");
        children = List.copyOf(
                Objects.requireNonNull(children, "children"));
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field);
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return normalized;
    }

    public boolean isLeaf() {
        return children.isEmpty();
    }
}
```

Tạo cây:

```java
CategoryNode root = new CategoryNode(
        "ROOT",
        "Products",
        List.of(
                new CategoryNode(
                        "BOOKS",
                        "Books",
                        List.of(
                                new CategoryNode("JAVA", "Java Books", List.of()),
                                new CategoryNode("DB", "Database Books", List.of())
                        )
                ),
                new CategoryNode(
                        "DEVICES",
                        "Devices",
                        List.of()
                )
        )
);
```

Mỗi node có cùng cấu trúc: mã, tên và danh sách node con. Phương thức `isLeaf()` chỉ dựa vào component nên record vẫn phù hợp; không cần class mutable chỉ vì dữ liệu có đệ quy.

### 4.2. Đọc cây bằng đệ quy

```java
public static void printTree(CategoryNode node, int depth) {
    System.out.println("  ".repeat(depth) + node.name());

    for (CategoryNode child : node.children()) {
        printTree(child, depth + 1);
    }
}
```

Gọi `printTree(root, 0)` sẽ duyệt từ node gốc xuống các node con. Cấu trúc immutable giúp cây không bị thay đổi bất ngờ trong lúc duyệt. Với cây rất sâu do dữ liệu đầu vào không tin cậy, nên cân nhắc giới hạn độ sâu hoặc dùng thuật toán duyệt lặp để tránh tràn stack.

### 4.3. Những quy tắc bổ sung cho cây

`List.copyOf` ngăn sửa danh sách con sau khi tạo node, nhưng chưa tự kiểm tra mọi bất biến của toàn cây. Tùy miền dữ liệu, có thể cần kiểm tra thêm:

- Mã node có duy nhất trong toàn cây hay chỉ trong từng cấp?
- Một node có được xuất hiện ở nhiều nhánh không?
- Có giới hạn số node hoặc độ sâu không?
- Cấu trúc phải là cây thực sự hay là đồ thị có liên kết dùng chung?
- Có cần thứ tự ổn định cho các node con không?

Nếu cần tham chiếu cha, cập nhật node, hoặc liên kết vòng giữa các node, mô hình record đệ quy thuần túy có thể không còn phù hợp. Khi đó hãy cân nhắc class/entity quản lý danh tính và vòng đời, hoặc mô hình đồ thị bằng ID và bảng tra cứu. Đừng cố nhét mọi quan hệ vào một cây JSON lồng sâu.

## 5. Kết hợp record generic và metadata

Nhiều phản hồi API có cùng một cấu trúc bao ngoài nhưng payload khác nhau. Generic record giúp tái sử dụng cấu trúc mà vẫn giữ kiểu dữ liệu cụ thể.

```java
import java.util.List;
import java.util.Objects;

public record Page<T>(
        List<T> items,
        Page.Pagination pagination
) {
    public Page {
        items = List.copyOf(Objects.requireNonNull(items, "items"));
        Objects.requireNonNull(pagination, "pagination");
    }

    public record Pagination(
            int pageNumber,
            int pageSize,
            long totalElements
    ) {
        public Pagination {
            if (pageNumber < 0 || pageSize <= 0 || totalElements < 0) {
                throw new IllegalArgumentException("Invalid pagination");
            }
        }
    }
}
```

Sử dụng cùng nhiều kiểu payload:

```java
Page<CustomerProfile> customerPage = new Page<>(
        List.of(profile),
        new Page.Pagination(0, 20, 1)
);

Page<CategoryNode> categoryPage = new Page<>(
        List.of(root),
        new Page.Pagination(0, 10, 1)
);
```

`Page<T>` giữ cấu trúc danh sách và phân trang chung. `Page.Pagination` là nested record vì nó là metadata đi cùng kiểu bao trang và không cần một instance `Page` để tồn tại.

Một lưu ý: component `items` chỉ được sao chép danh sách ở mức nông. Nếu `T` là kiểu mutable, người gọi vẫn có thể quan sát thay đổi bên trong phần tử. Khi muốn page là snapshot bất biến, hãy dùng payload bất biến hoặc chuyển đổi từng phần tử thành kiểu snapshot.

## 6. Chọn nơi khai báo kiểu con

Không phải mọi record con đều nên đặt bên trong record cha. Hãy chọn theo phạm vi sử dụng và ý nghĩa API.

| Cách khai báo | Nên dùng khi | Ví dụ |
|---|---|---|
| Nested record công khai | Kiểu con là phần của hợp đồng kiểu cha và ít được dùng độc lập | `CustomerProfile.Address` |
| Record top-level | Kiểu con được chia sẻ giữa nhiều API, module hoặc miền nghiệp vụ | `Address` dùng trong hồ sơ, đơn hàng, giao hàng |
| Nested record package-private | Kiểu con chỉ phục vụ nội bộ package và không cần public API | Kiểu projection nội bộ |
| Local record | Kiểu trung gian chỉ có ý nghĩa trong một phương thức/block | `RegionKey` dùng khi nhóm dữ liệu |

### 6.1. Khi nested record làm API rõ hơn

Dùng `CustomerProfile.Address` khi đọc tên kiểu đã thấy quan hệ sở hữu. Việc gom nhóm cũng tránh tạo nhiều tên top-level chung chung như `Address`, `Metadata` hoặc `Item` trong toàn package.

### 6.2. Khi nên tách thành top-level record

Nếu `Address` được dùng trong `CustomerProfile`, `ShippingRequest` và `InvoiceResponse` với cùng ngữ nghĩa, hãy cân nhắc một record top-level dùng chung. Nếu mỗi nơi có ý nghĩa hoặc quy tắc khác nhau, đừng ép chúng dùng chung chỉ vì có cùng vài trường.

Tái sử dụng kiểu dữ liệu có thể làm các API phụ thuộc vào nhau. Một thay đổi ở record dùng chung có thể ảnh hưởng nhiều nơi; đôi khi tạo hai record có cấu trúc tương tự nhưng hợp đồng riêng sẽ dễ bảo trì hơn.

### 6.3. Giữ cấu trúc nông vừa đủ

Ví dụ cấu trúc dễ hiểu:

```text
CustomerProfile
├── Address
└── Contacts
    ├── Contact
    └── Contact
```

Nếu dữ liệu trở thành nhiều tầng không có ý nghĩa tên gọi:

```text
Response
└── Data
    └── Payload
        └── Details
            └── Items
```

hãy xem lại các lớp bao. Mỗi tầng nên đại diện cho một khái niệm có ý nghĩa với người dùng API hoặc miền nghiệp vụ. Độ sâu không tự làm cấu trúc tốt hơn; nó có thể khiến truy cập dữ liệu và thay đổi hợp đồng khó khăn.

## 7. Tích hợp JSON, API và tầng lưu trữ

### 7.1. Ánh xạ JSON đệ quy

Các thư viện JSON hiện đại có hỗ trợ record có thể ánh xạ cấu trúc lồng nhau bằng cách tạo record ngoài và record con thông qua constructor tương ứng. Tuy nhiên, mức hỗ trợ phụ thuộc phiên bản thư viện, cấu hình, quy tắc tên thuộc tính và kiểu dữ liệu cụ thể.

Khi tích hợp:

- Chọn phiên bản thư viện có hỗ trợ record rõ ràng.
- Kiểm thử cả deserialize và serialize cho record ngoài, record con và collection.
- Đảm bảo tên JSON tương ứng với component hoặc khai báo mapping tường minh khi tên khác nhau.
- Kiểm tra cách xử lý trường bị thiếu, giá trị `null`, enum, thời gian và kiểu số.
- Đặt validation trong constructor để dữ liệu sai không tạo được object hợp lệ, đồng thời chuyển lỗi thành phản hồi API thích hợp.

Không nên mặc định rằng mọi framework cũ đều hỗ trợ record chỉ vì code Java biên dịch thành công.

### 7.2. Nested record không tự động là schema cơ sở dữ liệu

Một DTO record có nested record không có nghĩa ORM sẽ tự động lưu toàn bộ cấu trúc đó thành các bảng hoặc embedded columns. Entity, embeddable, projection và DTO là những khái niệm persistence khác nhau. Hãy kiểm tra khả năng của phiên bản ORM đang dùng và xác định rõ ranh giới mapping.

Thông thường, có thể dùng record để nhận kết quả truy vấn hoặc tạo response; việc quản lý entity có danh tính và vòng đời vẫn do mô hình persistence phù hợp đảm nhiệm.

### 7.3. Thay đổi cấu trúc là thay đổi hợp đồng

Thêm, xóa, đổi tên hoặc đổi kiểu một component có thể ảnh hưởng:

- Nơi gọi canonical constructor.
- Code truy cập accessor.
- Mapping JSON và client API.
- Serialization/deserialization và dữ liệu đã lưu.
- Projection hoặc mapping trong repository.

Với API công khai, hãy đánh giá tương thích ngược trước khi thay đổi. Nếu một nhóm trường thay đổi theo nhịp riêng, cân nhắc một kiểu con hoặc endpoint/version riêng thay vì liên tục sửa record bao ngoài. Tránh thêm component chỉ để đáp ứng một client riêng lẻ nếu nó làm hợp đồng chung trở nên khó hiểu.

## 8. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nested record giữ collection mutable trực tiếp | Dữ liệu có thể thay đổi qua tham chiếu bên ngoài | Dùng bản sao phòng vệ; cân nhắc phần tử bất biến |
| Chỉ validate record ngoài | Record con có thể tồn tại với dữ liệu sai | Đặt invariant trong constructor của từng record |
| Lồng record quá sâu | Khó đọc, khó truy cập và khó version API | Đặt tên tầng theo khái niệm; tách kiểu dùng chung |
| Dùng nested record cho kiểu được nhiều miền chia sẻ | Các miền phụ thuộc vào một API bao ngoài | Chuyển kiểu dùng chung thành top-level khi hợp lý |
| Nghĩ nested record cần outer instance | Khởi tạo sai cú pháp và hiểu nhầm vòng đời | Dùng `Outer.Inner` vì nested record ngầm định static |
| Cho rằng record lồng nhau là entity ORM | Sai kỳ vọng về mapping và lifecycle | Phân biệt DTO/projection với entity/embeddable |
| Cho rằng `List.copyOf` sao chép sâu | Phần tử mutable vẫn thay đổi được | Dùng kiểu phần tử bất biến hoặc chuyển đổi từng phần tử |
| Công khai component nội bộ không cần thiết | Khó thay đổi cấu trúc mà không phá API | Chỉ công khai các component thuộc hợp đồng |

## 9. Checklist thiết kế

Trước khi đưa cấu trúc nested record vào ứng dụng, hãy kiểm tra:

1. Mỗi tầng có đại diện cho một khái niệm dữ liệu có tên rõ ràng không?
2. Kiểu con chỉ thuộc về kiểu bao ngoài hay cần dùng lại ở nơi khác?
3. Nested record có được dùng như kiểu static độc lập, không phụ thuộc instance bên ngoài?
4. Mỗi record có tự xác thực các invariant của mình không?
5. Collection đã được sao chép phòng vệ chưa? Các phần tử có bất biến không?
6. Nếu là cây, đã xác định quy tắc duy nhất, độ sâu, số node và quan hệ cha/con chưa?
7. Framework JSON/persistence thực tế có hỗ trợ cấu trúc record đang dùng không?
8. Thay đổi component có làm thay đổi public API hoặc phá tương thích client không?
9. Có thể bỏ bớt một tầng bao mà vẫn giữ ngữ nghĩa rõ ràng không?

## 10. Bài tập vận dụng

**Bài 1 — DTO hồ sơ:** Thiết kế `EmployeeProfile` gồm mã nhân viên, `PersonalInfo`, `DepartmentInfo` và danh sách `EmergencyContact`. Chọn kiểu nào là nested record, kiểu nào là top-level. Viết compact constructor kiểm tra dữ liệu bắt buộc và sao chép danh sách.

**Bài 2 — Cây danh mục:** Tạo `CategoryNode` có mã, tên và danh sách node con. Viết hàm đệ quy đếm tổng số node, tính độ sâu lớn nhất và in cây theo cấp. Thử dữ liệu rỗng, node lá và cây nhiều tầng.

**Bài 3 — Phân trang generic:** Tạo `Page<T>` với danh sách items và nested `Pagination`. Kiểm tra trường hợp page size bằng 0, số trang âm và danh sách đầu vào bị thay đổi sau khi tạo Page.

**Bài 4 — Local record:** Trong một phương thức thống kê, khai báo local record làm khóa nhóm theo thành phố và mã bưu chính. Dùng `distinct()` hoặc `groupingBy()` để loại trùng và giải thích vì sao equality theo component hữu ích.

**Bài 5 — Hợp đồng JSON:** Chuyển `CustomerProfile` thành JSON và deserialize trở lại. Thử trường bị thiếu, `null` ở address, contacts có phần tử `null` và tên thuộc tính không khớp. Ghi lại cách thư viện đang dùng báo lỗi.

---

**Ghi nhớ:** Nested record giúp đặt kiểu con đúng phạm vi và mô tả dữ liệu nhiều tầng bằng composition. Java 16 đã chuẩn hóa nested và local record; chúng vẫn hữu ích trong Java hiện đại khi mỗi tầng có tên, invariant và vai trò rõ ràng. Hãy giữ collection và phần tử an toàn, tránh lồng sâu vô nghĩa, và xem component công khai là một phần của hợp đồng dữ liệu.
