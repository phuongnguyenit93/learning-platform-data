# Tên đầy đủ

Trong quá trình **phân giải tên** (*name resolution*) của một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), công cụ cần xác định mỗi tên trong chương trình đang tham chiếu đến khai báo nào. Một tên ngắn như `Customer`, `create` hoặc `status` có thể xuất hiện ở nhiều module, namespace hoặc phạm vi khác nhau. Nếu chỉ dựa vào phần tên cuối, công cụ có thể không biết người viết muốn dùng thành phần nào.

**Tên đầy đủ** (*fully qualified name – FQN*) là tên xác định một thành phần bằng cách kết hợp tên của nó với đường dẫn namespace, module, package hoặc phạm vi chứa nó. Tên đầy đủ giúp chỉ ra danh tính của thành phần một cách rõ ràng, giảm sự phụ thuộc vào ngữ cảnh hiện tại và hạn chế xung đột tên.

Ví dụ, hai module có thể cùng định nghĩa kiểu `Customer`:

```text
sales.Customer
support.Customer
```

Tên `Customer` đứng riêng có thể mơ hồ nếu cả hai module đều nằm trong phạm vi tra cứu. Hai tên đầy đủ cho biết rõ kiểu nào được tham chiếu.

Trong DSL, tên đầy đủ có thể dùng để tham chiếu kiểu, hàm, tài nguyên, quy tắc, bảng dữ liệu, workflow, module hoặc bất kỳ symbol nào có namespace. Cú pháp cụ thể tùy ngôn ngữ: có thể dùng dấu chấm, dấu `::`, dấu gạch chéo hoặc một cấu trúc phân cấp khác.

## 1. Tên đơn giản và tên đầy đủ

Một tên có thể được viết ở nhiều mức độ qualification (định danh phạm vi):

- **Tên đơn giản** (*simple/unqualified name*): chỉ có tên của symbol, ví dụ `Customer`.
- **Tên được định danh một phần** (*partially qualified name*): có một phần đường dẫn, ví dụ `sales.Customer` khi module `sales` còn nằm trong một namespace lớn hơn.
- **Tên đầy đủ** (*fully qualified name*): chứa đủ đường dẫn theo quy tắc của hệ thống để xác định duy nhất symbol, ví dụ `com.example.sales.Customer`.

Giả sử một dự án có cấu trúc:

```text
company
└── commerce
    ├── sales
    │   └── Customer
    └── support
        └── Customer
```

Các cách viết có thể được hiểu như sau:

| Cách viết | Loại tên | Ý nghĩa |
|---|---|---|
| `Customer` | Tên đơn giản | Cần ngữ cảnh để tìm symbol |
| `sales.Customer` | Định danh một phần | Chỉ rõ module `sales` trong một namespace đã biết |
| `company.commerce.sales.Customer` | Tên đầy đủ | Chỉ rõ đường dẫn đến kiểu trong namespace gốc |

Tên đầy đủ thường có thể xác định symbol mà không cần dựa vào import hoặc namespace hiện tại, miễn là tên đó được viết theo quy tắc toàn cục của DSL.

### 1.1. Tên đơn giản phụ thuộc vào ngữ cảnh

Trong một module có khai báo:

```text
module sales {
    model Customer {
        id: CustomerId
    }
}
```

Tên `CustomerId` có thể được tìm trong module hiện tại, namespace cha hoặc các import mà DSL cho phép. Người đọc cần biết môi trường phân giải tên để xác định symbol.

Trong module khác, cùng tên `CustomerId` có thể chỉ một kiểu khác. Vì vậy, tên đơn giản thuận tiện khi ngữ cảnh rõ ràng, nhưng không phải lúc nào cũng đủ để xác định danh tính.

### 1.2. Tên đầy đủ giảm phụ thuộc ngữ cảnh

Nếu viết:

```text
field customer: company.commerce.sales.Customer
```

công cụ có thể xác định kiểu `Customer` trong module `sales` mà không cần đoán từ các khai báo cùng tên ở module khác.

Tên đầy đủ đặc biệt hữu ích trong:

- Khai báo API công khai hoặc schema được chia sẻ giữa nhiều module.
- Tệp cấu hình độc lập, không có một namespace hiện hành rõ ràng.
- Tham chiếu đến kiểu hoặc tài nguyên từ nhiều package.
- Thông báo lỗi và công cụ điều hướng.
- Serialization, metadata hoặc định dạng lưu trữ cần giữ danh tính symbol.

## 2. Namespace, module và package

Tên đầy đủ thường được xây dựng từ các thành phần phân cấp. Các khái niệm namespace, module và package có liên quan nhưng không hoàn toàn giống nhau trong mọi hệ thống.

### 2.1. Namespace

**Namespace** là không gian tên dùng để nhóm các symbol và tránh trùng tên. Một namespace có thể chứa kiểu, hàm, hằng số, tài nguyên hoặc namespace con.

Ví dụ:

```text
namespace commerce.sales {
    model Customer { }
    model Order { }
}
```

Các tên đầy đủ có thể là:

```text
commerce.sales.Customer
commerce.sales.Order
```

Namespace tạo một đường dẫn logic. Nó không nhất thiết tương ứng với một thư mục hoặc một tệp vật lý.

### 2.2. Module

**Module** là đơn vị tổ chức và đóng gói các thành phần của chương trình. Module có thể quy định phần nào được công khai, phần nào chỉ dùng nội bộ, cùng các dependency hoặc quyền truy cập.

Ví dụ:

```text
module billing {
    public model Invoice { }
    internal model InvoiceDraft { }
}
```

Tên đầy đủ của `Invoice` có thể được dùng từ module khác nếu nó được export. Dù tên đã đầy đủ, việc truy cập vẫn có thể bị từ chối nếu symbol không công khai hoặc module chưa được khai báo dependency.

### 2.3. Package

Trong một số ngôn ngữ, package là đơn vị nhóm các kiểu và namespace. Ví dụ Java dùng tên package phân cấp:

```java
package com.example.sales;

public class Customer {
}
```

Tên đầy đủ của kiểu là:

```java
com.example.sales.Customer
```

DSL có thể dùng package, module hoặc namespace làm các phần của tên đầy đủ. Cần đọc đúng khái niệm mà ngôn ngữ cụ thể định nghĩa, không nên mặc định chúng luôn đồng nhất.

### 2.4. Phân cấp tên

Một tên đầy đủ thường được hình thành bằng cách nối các thành phần theo thứ tự từ phạm vi ngoài đến symbol cuối:

```text
root.namespace.module.symbol
```

Ví dụ:

```text
acme.platform.deploy.Resource
```

Trong đó:

- `acme` là namespace gốc.
- `platform` là namespace con.
- `deploy` là module hoặc namespace con.
- `Resource` là symbol được tham chiếu.

Tên đầy đủ phải tuân theo grammar của DSL. Dấu phân cách có thể là `.` hoặc `::`, và một số ngôn ngữ có cú pháp riêng cho tên toàn cục.

## 3. Cú pháp của tên đầy đủ

DSL cần định nghĩa cách viết tên được qualification. Những lựa chọn phổ biến gồm:

### 3.1. Dùng dấu chấm

```text
company.sales.Customer
```

Cú pháp này ngắn gọn và quen thuộc trong nhiều ngôn ngữ. Tuy nhiên, nếu dấu chấm cũng dùng cho truy cập thuộc tính (`order.customer.name`), parser hoặc semantic analysis cần phân biệt tên phân cấp với chuỗi truy cập thuộc tính theo ngữ cảnh.

### 3.2. Dùng dấu `::`

```text
company::sales::Customer
```

Dấu `::` thường được dùng để phân tách namespace hoặc phạm vi. Nó giúp phân biệt đường dẫn tên với toán tử truy cập thuộc tính dùng dấu chấm.

Ví dụ trong Rust:

```rust
std::collections::HashMap
```

Đây là đường dẫn đến kiểu `HashMap` trong module `collections` thuộc `std`.

### 3.3. Dùng dấu gạch chéo hoặc đường dẫn

Một DSL quản lý tài nguyên có thể dùng:

```text
organizations/acme/projects/commerce/resources/catalog
```

Đường dẫn này có thể là tên đầy đủ của tài nguyên theo cấu trúc miền. Cần phân biệt tên logic với đường dẫn tệp hệ điều hành; hai loại có thể dùng cùng dấu `/` nhưng có quy tắc chuẩn hóa khác nhau.

### 3.4. Tên toàn cục

Một số ngôn ngữ cho phép ký hiệu đặc biệt để chỉ bắt đầu tra cứu từ namespace gốc, tránh bị ảnh hưởng bởi namespace hiện tại.

Ví dụ cú pháp giả định:

```text
::company::sales::Customer
```

Tiền tố `::` có thể biểu thị tra cứu từ root namespace. Đây chỉ là quy ước minh họa; DSL cụ thể phải định nghĩa rõ ký hiệu bắt đầu đường dẫn toàn cục.

### 3.5. Tên có tham số kiểu

Nếu DSL hỗ trợ kiểu generic, tên đầy đủ có thể kết hợp với tham số kiểu:

```text
collections.List<company.sales.Customer>
```

Ở đây tên `List` được qualification, còn kiểu phần tử `Customer` cũng được qualification. Một số ngôn ngữ biểu diễn generic bằng dấu ngoặc vuông hoặc cú pháp khác.

## 4. Phân giải tên đầy đủ

Phân giải tên là quá trình biến tên được viết trong chương trình thành tham chiếu đến symbol đã được khai báo. Với tên đầy đủ, công cụ thường có thể đi theo từng thành phần của đường dẫn thay vì tìm kiếm trong nhiều phạm vi cùng lúc.

Giả sử có các khai báo:

```text
namespace acme.crm {
    model Customer { }
}

namespace acme.billing {
    model Invoice {
        customer: acme.crm.Customer
    }
}
```

Khi phân giải `acme.crm.Customer`, công cụ có thể thực hiện:

1. Tìm namespace gốc `acme`.
2. Tìm namespace con `crm` trong `acme`.
3. Tìm symbol `Customer` trong `acme.crm`.
4. Kiểm tra symbol có thể truy cập từ module hiện tại không.
5. Gắn tham chiếu đã phân giải vào AST hoặc symbol table.

Kết quả không chỉ là chuỗi văn bản. Công cụ nên lưu một symbol identity hoặc symbol reference trỏ đến khai báo thực tế.

### 4.1. Phân giải theo từng thành phần

Với tên `a.b.c`, một thuật toán có thể:

- Phân giải `a` trong phạm vi gốc hoặc phạm vi được chỉ định.
- Từ symbol `a`, tra thành phần con `b`.
- Từ symbol `b`, tra thành phần con `c`.
- Kiểm tra loại symbol và quyền truy cập tại mỗi bước.

Nếu `a` không tồn tại, công cụ có thể báo lỗi ngay ở thành phần đầu. Nếu `a` tồn tại nhưng không chứa `b`, lỗi nên chỉ rõ đường dẫn bị đứt ở `b`.

### 4.2. Kiểm tra khả năng truy cập

Tên đầy đủ không tự động vượt qua quy tắc visibility. Nếu `internal.Customer` là symbol nội bộ của module `internal`, một module khác không thể truy cập nó chỉ bằng cách viết đủ đường dẫn.

Phân giải tên thường cần kiểm tra:

- Symbol có tồn tại không?
- Module chứa symbol có được dependency hiện tại tham chiếu không?
- Symbol có được export hoặc công khai không?
- Có quy tắc friend module hoặc quyền đặc biệt nào không?
- Phiên bản module có tương thích không?

Do đó, “đầy đủ” nói về mức độ qualification của tên, còn “được phép truy cập” là một điều kiện riêng.

## 5. Tên đầy đủ và import

Import cho phép đưa symbol hoặc namespace từ module khác vào phạm vi hiện tại để dùng tên ngắn hơn.

Ví dụ:

```text
import acme.crm.Customer

model Invoice {
    customer: Customer
}
```

Nếu import hợp lệ, tên `Customer` có thể được phân giải đến `acme.crm.Customer`.

Tên đầy đủ vẫn hữu ích ngay cả khi có import:

```text
model Invoice {
    customer: acme.crm.Customer
}
```

Cách viết thứ hai làm rõ nguồn của kiểu ngay tại nơi sử dụng và tránh phụ thuộc vào một import ở đầu tệp.

### 5.1. Import một symbol

```text
import acme.crm.Customer
```

Import một symbol thường đưa tên cuối `Customer` vào phạm vi hiện tại.

### 5.2. Import namespace hoặc module

```text
import acme.crm
```

Sau đó, người viết có thể dùng:

```text
crm.Customer
```

hoặc cú pháp tương ứng mà DSL quy định. Import namespace có thể làm tăng nguy cơ trùng tên nếu nhiều namespace có cùng tên thành phần.

### 5.3. Import tất cả (wildcard import)

```text
import acme.crm.*
```

Wildcard import có thể đưa nhiều symbol vào phạm vi. Nó giảm số dòng import nhưng khiến nguồn gốc của tên đơn giản khó nhìn thấy hơn và có thể gây xung đột khi module bổ sung symbol mới.

Một DSL có thể cấm wildcard import, giới hạn nó ở một số module hoặc xác định thứ tự ưu tiên rõ ràng.

### 5.4. Import có bí danh

Nếu hai module có tên trùng, bí danh (*alias*) giúp phân biệt:

```text
import acme.crm as crm
import acme.support as support

model Ticket {
    requester: crm.Customer
    assignedAgent: support.Customer
}
```

Bí danh tạo đường dẫn ngắn hơn nhưng vẫn giữ được nguồn gốc. Khi cần tham chiếu độc lập với alias cục bộ, có thể dùng tên đầy đủ.

## 6. Tên đầy đủ và tên tương đối

Một tên tương đối (*relative name*) được phân giải dựa trên namespace, module hoặc phạm vi hiện tại. Tên đầy đủ thường bắt đầu từ một gốc được xác định theo quy tắc DSL.

Ví dụ, trong namespace `acme.sales.eu`:

```text
model Order {
    customer: Customer
    address: common.Address
}
```

Tên `Customer` có thể được tìm trong namespace hiện tại hoặc các import. Tên `common.Address` có thể được tìm tương đối từ một namespace cha hoặc alias đã khai báo. Tên đầy đủ có thể là:

```text
acme.sales.Customer
acme.common.Address
```

### 6.1. Quy tắc bắt đầu đường dẫn

DSL cần xác định tên có qualification một phần được tra từ đâu:

- Từ namespace hiện tại.
- Từ namespace cha gần nhất.
- Từ các import hoặc alias.
- Từ namespace gốc.

Nếu không có quy tắc rõ, cùng một tên `common.Address` có thể được hiểu khác nhau trong hai module.

### 6.2. Đường dẫn tuyệt đối và tương đối

Một số ngôn ngữ dùng tiền tố để phân biệt đường dẫn tuyệt đối với đường dẫn tương đối. Một số khác luôn xem tên có dấu phân cách là tương đối trước rồi mới thử global. Cách xử lý phải được đặc tả, không nên để thứ tự thử ngầm trở thành hành vi khó dự đoán.

### 6.3. Tên tương đối có thể tiện, tên đầy đủ có thể ổn định

Tên tương đối ngắn gọn và giúp mã dễ đọc trong module. Tên đầy đủ hữu ích ở ranh giới module, API công khai hoặc cấu hình cần đứng độc lập. Nhiều DSL hỗ trợ cả hai để cân bằng khả năng đọc và tính rõ ràng.

## 7. Xung đột tên và tính mơ hồ

Xung đột tên xảy ra khi nhiều symbol có cùng tên trong những phạm vi có thể được tra cứu cùng lúc.

Ví dụ:

```text
import acme.crm.Customer
import acme.support.Customer

model Case {
    owner: Customer
}
```

Tên `Customer` có thể chỉ đến hai kiểu khác nhau. Nếu DSL không có quy tắc ưu tiên rõ, công cụ nên báo lỗi mơ hồ thay vì chọn ngẫu nhiên.

### 7.1. Dùng tên đầy đủ để giải quyết mơ hồ

```text
model Case {
    requester: acme.crm.Customer
    agent: acme.support.Customer
}
```

Hai tham chiếu đã được qualification đầy đủ nên không còn xung đột ở tên cuối.

### 7.2. Quy tắc ưu tiên khi phân giải tên ngắn

Một DSL có thể xác định thứ tự tra cứu, chẳng hạn:

1. Phạm vi cục bộ.
2. Phạm vi khai báo bao quanh.
3. Namespace hiện tại.
4. Import tường minh.
5. Import wildcard.
6. Namespace gốc hoặc thư viện chuẩn.

Thứ tự trên chỉ là ví dụ. Các ngôn ngữ có thể chọn thứ tự khác. Nếu hai symbol cùng mức ưu tiên đều phù hợp, công cụ nên báo lỗi mơ hồ.

### 7.3. Không nên dựa vào thứ tự import để chọn symbol

Nếu hai import cùng đưa `Customer` vào phạm vi, chọn import xuất hiện sau có thể khiến việc đổi thứ tự dòng import làm thay đổi ý nghĩa chương trình. Đây là hành vi khó đoán và dễ gây lỗi.

Một thiết kế rõ ràng có thể:

- Báo lỗi khi tên bị trùng.
- Yêu cầu alias cho ít nhất một import.
- Yêu cầu tên đầy đủ tại điểm sử dụng.

## 8. Tên đầy đủ và symbol identity

Tên đầy đủ là cách biểu diễn có thể đọc được của một symbol, nhưng trong compiler hoặc DSL engine, danh tính nội bộ của symbol không nhất thiết chỉ là chuỗi tên.

Một symbol có thể được biểu diễn bằng:

- Symbol ID duy nhất trong lần phân tích.
- Module ID cộng với local name.
- Namespace path và declaration ID.
- URI hoặc định danh ổn định của tài nguyên.

Ví dụ:

```text
Symbol {
    id: 8f31...
    module: acme.crm
    name: Customer
    kind: Model
}
```

Tên đầy đủ `acme.crm.Customer` có thể được dùng để hiển thị, trong khi `id` là khóa nội bộ để liên kết tham chiếu đến đúng khai báo.

### 8.1. Vì sao không chỉ lưu chuỗi tên?

Nếu chỉ lưu chuỗi, các bước sau có thể phải phân giải lại tên và có nguy cơ hiểu khác nếu import hoặc namespace thay đổi. Symbol reference giúp AST, IR, validator và code generator cùng trỏ đến một khai báo đã được xác định.

### 8.2. Tên đầy đủ có thể thay đổi

Nếu một module được chuyển namespace hoặc đổi tên, FQN có thể thay đổi dù symbol về mặt nghiệp vụ vẫn là thành phần đó. Nếu hệ thống cần định danh ổn định qua các lần đổi tên, nên có symbol ID hoặc migration mapping.

## 9. Chuẩn hóa tên đầy đủ

Chuẩn hóa (*canonicalization*) là việc chuyển các cách biểu diễn tương đương về một dạng chuẩn. Tên đầy đủ thường cần chuẩn hóa để so sánh, lưu trữ, cache hoặc trao đổi giữa các công cụ.

Những quyết định cần xác định:

- Tên có phân biệt chữ hoa và chữ thường không?
- Có chuẩn hóa Unicode không?
- Có cho phép alias trong tên được lưu hay chỉ dùng khi viết mã?
- Dấu phân cách có một dạng chuẩn duy nhất không?
- Có bỏ khoảng trắng hoặc escape đặc biệt không?
- Tên có chứa phiên bản module hay namespace không?

Ví dụ, nếu DSL không phân biệt hoa thường, `Sales.Customer` và `sales.customer` có thể được chuẩn hóa về cùng một tên. Nếu DSL phân biệt hoa thường, chúng là hai tên khác nhau.

### 9.1. Chuẩn hóa Unicode

Hai chuỗi Unicode có thể nhìn giống nhau nhưng có biểu diễn code point khác nhau. Nếu DSL cho phép Unicode trong định danh, cần quyết định có chuẩn hóa theo một dạng Unicode như NFC hay không.

Việc chuẩn hóa cần nhất quán giữa lexer, symbol table, import, filesystem và các công cụ tích hợp. Không nên chuẩn hóa tùy tiện nếu hệ thống bên ngoài xem hai chuỗi đó là khác nhau.

### 9.2. Escape ký tự đặc biệt

Nếu tên namespace có thể chứa ký tự trùng với dấu phân cách, DSL cần cú pháp escape hoặc giới hạn tập ký tự cho định danh.

Ví dụ, nếu `.` là dấu phân cách, một tên thành phần có dấu chấm bên trong cần được escape hoặc đặt trong dấu nháy theo quy tắc rõ ràng. Nếu không, parser không thể biết dấu chấm thuộc tên hay phân tách namespace.

## 10. Tên đầy đủ trong các loại symbol

Tên đầy đủ không chỉ áp dụng cho kiểu dữ liệu. Tùy DSL, nhiều loại symbol có thể được qualification.

### 10.1. Kiểu và model

```text
field customer: acme.crm.Customer
```

Tham chiếu đến kiểu hoặc model được định nghĩa trong namespace khác.

### 10.2. Hàm và thao tác

```text
result = acme.math.statistics.mean(values)
```

Đường dẫn chỉ ra hàm `mean` thuộc module `statistics` trong namespace `acme.math`.

### 10.3. Tài nguyên

```text
dependsOn: cloud.compute.Instance
```

DSL hạ tầng có thể dùng tên đầy đủ để chỉ loại tài nguyên hoặc provider.

### 10.4. Bảng và schema dữ liệu

```text
from analytics.sales.Orders
```

Tên đầy đủ có thể phân biệt bảng `Orders` trong schema `sales` của database hoặc catalog `analytics` với bảng cùng tên ở nơi khác.

### 10.5. Quy tắc và workflow

```text
apply acme.compliance.rules.VerifyCustomer
run acme.fulfillment.workflow.DispatchOrder
```

Tên đầy đủ giúp tham chiếu chính xác quy tắc hoặc workflow được quản lý trong nhiều module.

## 11. Ví dụ phân giải tên trong một DSL mô hình

Giả sử dự án có hai namespace:

```text
namespace acme.crm {
    model Customer {
        id: String
        name: String
    }
}

namespace acme.support {
    model Customer {
        id: String
        supportLevel: Integer
    }

    model Ticket {
        requester: acme.crm.Customer
        assignedAgent: acme.support.Customer
    }
}
```

Trong `Ticket`, cả hai trường đều tham chiếu đến một model có tên cuối là `Customer`, nhưng mỗi trường có FQN khác nhau.

Một compiler có thể xây dựng symbol table:

| Tên đầy đủ | Loại symbol | Khai báo |
|---|---|---|
| `acme.crm.Customer` | Model | Model khách hàng của CRM |
| `acme.support.Customer` | Model | Model người dùng của bộ phận hỗ trợ |
| `acme.support.Ticket` | Model | Model phiếu hỗ trợ |

Khi phân tích `requester`, compiler lưu symbol reference đến `acme.crm.Customer`. Khi phân tích `assignedAgent`, compiler lưu reference đến `acme.support.Customer`.

Sau khi phân giải, code generator không cần đoán lại từ tên `Customer`; nó có thể dùng symbol identity đã được xác định.

## 12. Ví dụ Java: tên đầy đủ và import

Java là ví dụ quen thuộc về package và fully qualified name.

Giả sử có hai lớp:

```java
package com.example.crm;

public class Customer {
}
```

```java
package com.example.support;

public class Customer {
}
```

Trong một lớp khác, có thể dùng tên đầy đủ:

```java
public class TicketService {
    com.example.crm.Customer requester;
    com.example.support.Customer agent;
}
```

Hoặc import một kiểu rồi dùng tên đơn giản:

```java
import com.example.crm.Customer;

public class InvoiceService {
    Customer customer;
}
```

Nếu hai lớp cùng tên đơn giản được import theo cách gây xung đột, cần dùng tên đầy đủ tại điểm khai báo hoặc đổi cách tổ chức import. Java không hỗ trợ alias import kiểu tổng quát như một số ngôn ngữ khác.

Ví dụ này cho thấy tên đầy đủ và tên đơn giản là hai cách tham chiếu đến cùng một kiểu, nhưng tên đầy đủ thể hiện rõ package chứa kiểu.

## 13. Tên đầy đủ và phiên bản module

Trong hệ thống có nhiều phiên bản thư viện hoặc schema, tên đầy đủ có thể chưa đủ để xác định chính xác định nghĩa cần dùng. Cần phân biệt:

- Namespace hoặc module path.
- Phiên bản module hoặc package.
- Phiên bản schema hoặc API.
- Phiên bản runtime hoặc provider nếu ảnh hưởng đến ý nghĩa.

Ví dụ, hai phiên bản của một schema có thể cùng định nghĩa `Customer` nhưng khác trường hoặc quy tắc:

```text
acme.crm.v1.Customer
acme.crm.v2.Customer
```

Một cách khác là giữ FQN ổn định và để version được quản lý trong dependency declaration:

```text
dependency acme.crm version "2.1"
```

Khi đó, FQN được phân giải trong ngữ cảnh phiên bản dependency đã chọn. DSL cần xác định cách xử lý khi hai dependency yêu cầu các phiên bản không tương thích.

### 13.1. Version trong tên hay trong metadata?

Đưa version vào FQN làm cho tên thể hiện rõ phiên bản, nhưng có thể khiến mã nguồn phải đổi nhiều khi nâng cấp. Quản lý version ở metadata hoặc dependency thường giữ tên logic ổn định hơn, nhưng cần công cụ giải quyết dependency rõ ràng.

Không có một cách duy nhất phù hợp cho mọi DSL. Cần chọn dựa trên việc các phiên bản có phải những kiểu khác nhau cùng tồn tại hay chỉ là các lần phát hành của cùng một API.

## 14. Tên đầy đủ trong thông báo lỗi và công cụ phát triển

Tên đầy đủ giúp thông báo lỗi rõ hơn khi có nhiều symbol cùng tên.

Ví dụ:

```text
Ambiguous type 'Customer'. Candidates:
  - acme.crm.Customer
  - acme.support.Customer
Use a fully qualified name or import one type with an alias.
```

Một IDE cũng có thể hiển thị:

- FQN trong tooltip hoặc hover.
- Module và package chứa symbol.
- Đường dẫn đến khai báo.
- Tên đơn giản trong mã nhưng FQN trong danh sách gợi ý.
- Hành động tự thêm import hoặc qualification đầy đủ.

Khi rename symbol, công cụ cần cập nhật những tham chiếu đã được phân giải đến đúng symbol identity. Không nên thay mọi chuỗi có cùng tên đơn giản, vì một số chuỗi có thể tham chiếu đến symbol khác hoặc chỉ là dữ liệu văn bản.

## 15. Tên đầy đủ và serialization

Một số DSL lưu tham chiếu đến kiểu hoặc tài nguyên trong tệp cấu hình, database hoặc thông điệp truyền qua mạng. Khi đó, tên đầy đủ có thể được dùng làm định danh có thể lưu trữ.

Ví dụ:

```json
{
  "type": "acme.crm.Customer",
  "id": "C-1024"
}
```

Khi nạp lại, hệ thống dùng tên kiểu để tìm model tương ứng. Cách làm này cần cân nhắc:

- FQN có ổn định qua lần đổi tên hoặc chuyển module không?
- Có cần registry ánh xạ tên cũ sang tên mới không?
- Có cho phép dữ liệu không tin cậy chỉ định tên kiểu tùy ý không?
- Có cần allowlist các kiểu được phép nạp không?
- Phiên bản schema có được lưu cùng dữ liệu không?

Không nên tự động khởi tạo hoặc nạp bất kỳ kiểu nào chỉ vì dữ liệu đầu vào chứa một FQN. Hệ thống cần kiểm tra quyền và danh sách kiểu hợp lệ để tránh nạp thành phần không mong muốn.

## 16. Chiến lược sử dụng tên đầy đủ trong DSL

Một DSL có thể quy định khi nào bắt buộc dùng FQN và khi nào cho phép tên ngắn.

### 16.1. Bắt buộc FQN ở ranh giới module

Trong API công khai, schema chia sẻ hoặc cấu hình được lưu lâu dài, tên đầy đủ giúp tham chiếu ổn định và ít phụ thuộc import cục bộ.

### 16.2. Cho phép tên đơn giản trong phạm vi cục bộ

Trong cùng module hoặc namespace, tên ngắn giúp chương trình dễ đọc. Công cụ có thể tự phân giải dựa trên phạm vi hiện tại.

### 16.3. Dùng alias cho dependency dài

Alias giúp tránh lặp đường dẫn dài:

```text
import acme.platform.observability.metrics as metrics

metrics.Counter
metrics.Timer
```

Alias nên có phạm vi rõ ràng và không được làm thay đổi danh tính của symbol.

### 16.4. Dùng FQN khi có xung đột

Nếu tên ngắn có nhiều ứng viên, công cụ có thể yêu cầu qualification thay vì âm thầm chọn một symbol.

### 16.5. Giữ tên hiển thị và tên chuẩn riêng biệt

Tên hiển thị (*display name*) có thể thân thiện với người dùng, có dấu cách hoặc bản dịch. FQN nên là định danh kỹ thuật ổn định, có quy tắc ký tự và chuẩn hóa rõ ràng.

Ví dụ, tài nguyên có display name `Kho hàng miền Bắc` nhưng FQN có thể là `acme.inventory.warehouses.north`. Hai tên phục vụ hai mục đích khác nhau.

## 17. Những sai lầm thường gặp

**Cho rằng tên đầy đủ luôn bỏ qua mọi quy tắc truy cập.** FQN giúp xác định symbol, nhưng module visibility và dependency vẫn có thể ngăn truy cập.

**Nhầm tên đầy đủ với đường dẫn tệp.** Namespace logic không nhất thiết tương ứng với thư mục vật lý; đổi cấu trúc thư mục không luôn làm đổi FQN.

**Cho rằng tên có nhiều dấu chấm chắc chắn là FQN.** Một DSL có thể dùng dấu chấm cho thuộc tính hoặc biểu thức khác. Cần dựa vào grammar và ngữ cảnh.

**Dựa vào thứ tự import để giải quyết xung đột.** Cách này làm ý nghĩa chương trình phụ thuộc vào cách sắp xếp dòng import và khó bảo trì.

**Chỉ lưu chuỗi tên thay vì symbol reference.** Các bước sau có thể phải phân giải lại và vô tình trỏ đến symbol khác khi ngữ cảnh thay đổi.

**Không chuẩn hóa tên nhất quán.** Khác biệt hoa thường, Unicode hoặc dấu phân cách có thể khiến cùng một symbol được nhận diện thành nhiều tên.

**Đưa version vào tên mà không có chính sách migration.** Khi đổi phiên bản, tham chiếu lưu trữ có thể trở nên lỗi thời.

**Dùng FQN từ dữ liệu không tin cậy để nạp kiểu tùy ý.** Cần kiểm tra registry, allowlist và quyền truy cập trước khi tạo đối tượng.

## 18. Ghi nhớ

- Tên đầy đủ (*fully qualified name*) xác định symbol bằng đường dẫn namespace, module, package hoặc phạm vi chứa nó.
- Tên đơn giản ngắn gọn nhưng phụ thuộc ngữ cảnh; tên đầy đủ giúp tránh mơ hồ và giảm phụ thuộc vào import.
- Namespace, module và package là các khái niệm tổ chức tên có liên quan nhưng không nhất thiết đồng nghĩa.
- FQN có thể dùng cho kiểu, hàm, tài nguyên, bảng, schema, quy tắc và workflow.
- Phân giải tên đầy đủ cần kiểm tra cả sự tồn tại, dependency và quyền truy cập.
- Import và alias giúp viết tên ngắn hơn; khi có xung đột, công cụ nên yêu cầu alias hoặc qualification rõ ràng.
- Symbol identity nội bộ có thể ổn định hơn chuỗi FQN, nhất là khi module được đổi tên hoặc di chuyển.
- Chuẩn hóa tên cần xác định quy tắc hoa thường, Unicode, dấu phân cách và escape.
- FQN trong serialization cần có chính sách versioning, migration và kiểm soát kiểu được phép nạp.

## 19. Câu hỏi tự kiểm tra

1. Tên đầy đủ khác tên đơn giản ở điểm nào?
2. Vì sao hai module có thể cùng định nghĩa `Customer` mà không tạo xung đột nếu dùng FQN?
3. Namespace, module và package có vai trò gì trong việc tạo tên đầy đủ?
4. Phân giải `acme.crm.Customer` có thể được thực hiện theo những bước nào?
5. Tên đầy đủ có tự động cho phép truy cập một symbol `internal` không? Giải thích.
6. Import alias giải quyết vấn đề trùng tên như thế nào?
7. Phân biệt tên tương đối và tên bắt đầu từ namespace gốc.
8. Vì sao compiler nên lưu symbol reference thay vì chỉ giữ chuỗi FQN?
9. Những quy tắc nào cần được xác định khi chuẩn hóa tên Unicode?
10. Khi nào nên lưu FQN trong dữ liệu serialization và cần kiểm soát rủi ro gì?
11. Vì sao thứ tự import không nên âm thầm quyết định symbol được chọn?
12. Trong một DSL có hai kiểu `Customer`, hãy viết ví dụ tham chiếu cả hai kiểu bằng tên đầy đủ và giải thích cách compiler phân giải chúng.
