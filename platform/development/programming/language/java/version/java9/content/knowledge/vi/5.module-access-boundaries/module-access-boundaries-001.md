# `exports` và cách truy cập các kiểu `public` từ mô-đun bên ngoài

Trong Java Platform Module System (JPMS), từ khóa `public` và chỉ thị `exports` giải quyết hai lớp kiểm soát khác nhau. Một lớp có thể được khai báo `public` nhưng vẫn không thể được mã nguồn ở mô-đun khác sử dụng nếu package chứa lớp đó chưa được mô-đun sở hữu export.

Để mã trong mô-đun tiêu thụ dùng được một kiểu thuộc mô-đun cung cấp, thông thường cần đồng thời thỏa mãn ba điều kiện:

1. Mô-đun tiêu thụ **đọc được** mô-đun cung cấp, thường thông qua `requires`.
2. Mô-đun cung cấp **export package** chứa kiểu đó cho mô-đun tiêu thụ.
3. Kiểu và thành viên được sử dụng phải đáp ứng quy tắc truy cập của Java, ví dụ kiểu top-level và constructor/phương thức cần dùng phải là `public`.

Có thể nhớ ngắn gọn: `requires` tạo quan hệ đọc mô-đun; `exports` công khai một package; modifier như `public` quyết định kiểu hoặc thành viên nào trong package đó có thể được truy cập.

## 1. Khai báo `exports` trong `module-info.java`

Một named module khai báo package công khai trong module descriptor:

```java
module com.acme.billing {
    exports com.acme.billing.api;
}
```

Chỉ thị `exports com.acme.billing.api;` cho phép các mô-đun đọc được `com.acme.billing` truy cập những kiểu public trong package `com.acme.billing.api`, theo quy tắc truy cập Java.

`exports` áp dụng ở **cấp package**, không áp dụng riêng cho từng class. Một package được export có thể chứa nhiều class, interface, enum, record hoặc annotation public; tất cả đều thuộc phạm vi công khai của package đó nếu đáp ứng điều kiện truy cập.

Mô-đun tiêu thụ khai báo phụ thuộc:

```java
module com.acme.checkout {
    requires com.acme.billing;
}
```

Sau khi `com.acme.checkout` đọc được `com.acme.billing`, mã của nó có thể import và sử dụng kiểu public thuộc package đã export.

## 2. `public` không tự động vượt qua ranh giới mô-đun

Modifier `public` chỉ nói rằng kiểu hoặc thành viên có thể được truy cập theo quy tắc Java. Nó không tự đưa package vào API công khai của một named module.

Ví dụ, giả sử mô-đun `com.acme.billing` có hai package:

- `com.acme.billing.api`: chứa các kiểu được thiết kế cho consumer sử dụng.
- `com.acme.billing.internal`: chứa chi tiết triển khai nội bộ.

Nếu module descriptor chỉ có:

```java
module com.acme.billing {
    exports com.acme.billing.api;
}
```

thì `com.acme.billing.api.Invoice` có thể được consumer sử dụng nếu kiểu và thành viên cần dùng là public. Dù `com.acme.billing.internal.InternalTaxPolicy` được khai báo public, mô-đun khác vẫn không thể import nó vì package `com.acme.billing.internal` chưa được export.

Các điểm cần phân biệt:

- Một class public trong package không được export vẫn bị che khỏi mã của mô-đun khác.
- Export package không biến class package-private thành public.
- Thành viên private và package-private vẫn không truy cập trực tiếp được từ package khác.
- Thành viên protected tiếp tục tuân theo quy tắc truy cập protected của Java, đặc biệt là điều kiện kế thừa; nó không trở thành thành viên công khai cho mọi caller.
- Export một package không tự export các package con. `com.acme.billing.api.internal` là package riêng, cần được khai báo export riêng nếu thực sự muốn công khai.

Mô-đun vẫn có thể dùng các package chưa export từ bên trong chính nó. Cơ chế này giúp giữ phần triển khai nội bộ trong module mà không biến chúng thành API cho consumer.

## 3. Ví dụ chạy được với hai named module

Ví dụ sau có mô-đun cung cấp `com.acme.billing` và mô-đun tiêu thụ `com.acme.checkout`. Chỉ package `com.acme.billing.api` được export.

Cấu trúc thư mục:

```text
src/
├── com.acme.billing/
│   ├── module-info.java
│   └── com/acme/billing/
│       ├── api/Invoice.java
│       └── internal/InternalTaxPolicy.java
└── com.acme.checkout/
    ├── module-info.java
    └── com/acme/checkout/Main.java
```

**Mô-đun cung cấp — `src/com.acme.billing/module-info.java`:**

```java
module com.acme.billing {
    exports com.acme.billing.api;
}
```

**Kiểu public được công khai — `src/com.acme.billing/com/acme/billing/api/Invoice.java`:**

```java
package com.acme.billing.api;

import java.math.BigDecimal;
import java.util.Objects;

public final class Invoice {
    private final String number;
    private final BigDecimal total;

    public Invoice(String number, BigDecimal total) {
        this.number = Objects.requireNonNull(number);
        this.total = Objects.requireNonNull(total);
    }

    public String number() {
        return number;
    }

    public BigDecimal total() {
        return total;
    }
}
```

**Kiểu triển khai không export — `src/com.acme.billing/com/acme/billing/internal/InternalTaxPolicy.java`:**

```java
package com.acme.billing.internal;

public final class InternalTaxPolicy {
    public static String description() {
        return "internal";
    }
}
```

Class `InternalTaxPolicy` cố ý được khai báo public để cho thấy modifier `public` không thay thế được `exports`. Package `com.acme.billing.internal` vẫn nằm ngoài API của module.

**Mô-đun tiêu thụ — `src/com.acme.checkout/module-info.java`:**

```java
module com.acme.checkout {
    requires com.acme.billing;
}
```

**Chương trình tiêu thụ — `src/com.acme.checkout/com/acme/checkout/Main.java`:**

```java
package com.acme.checkout;

import com.acme.billing.api.Invoice;
import java.math.BigDecimal;

public final class Main {
    public static void main(String[] args) {
        Invoice invoice = new Invoice(
            "INV-2026-057",
            new BigDecimal("125.50")
        );

        System.out.println(
            invoice.number() + " | total=" + invoice.total()
        );
    }
}
```

Từ thư mục gốc chứa `src/`, dùng JDK 17 trở lên để biên dịch và chạy:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --module-source-path src -d out -m com.acme.billing,com.acme.checkout
java --module-path out -m com.acme.checkout/com.acme.checkout.Main
```

**Bash:**

```bash
mkdir -p out
javac --module-source-path src -d out -m com.acme.billing,com.acme.checkout
java --module-path out -m com.acme.checkout/com.acme.checkout.Main
```

Kết quả:

```text
INV-2026-057 | total=125.50
```

Ví dụ chứng minh consumer đọc được `Invoice` vì ba điều kiện đều đúng: `com.acme.checkout` yêu cầu `com.acme.billing`; package `com.acme.billing.api` được export; và class, constructor cùng các phương thức được sử dụng đều public.

Nếu thêm import sau vào `Main.java`:

```java
import com.acme.billing.internal.InternalTaxPolicy;
```

trình biên dịch sẽ từ chối vì package `com.acme.billing.internal` không được module `com.acme.billing` export. Việc class `InternalTaxPolicy` có modifier public không làm thay đổi kết quả đó.

## 4. Qualified exports — chỉ công khai cho mô-đun được chọn

Không phải package nào cũng cần mở cho mọi consumer. Có thể giới hạn phạm vi export bằng danh sách tên mô-đun:

```java
module com.acme.billing {
    exports com.acme.billing.api
        to com.acme.checkout, com.acme.reporting;
}
```

Đây là **qualified export**:

- `com.acme.checkout` và `com.acme.reporting` có thể truy cập các kiểu public trong package đã chỉ định nếu chúng đọc được `com.acme.billing`.
- Một mô-đun khác dù khai báo `requires com.acme.billing;` vẫn không được truy cập package đó.
- Mỗi mô-đun được nêu trong mệnh đề `to` phải dùng đúng tên mô-đun trong module descriptor của nó.

Qualified export hữu ích khi một API chỉ phục vụ một nhóm mô-đun cộng tác đã biết. Với API thư viện dành cho nhiều consumer độc lập, unqualified export thường phù hợp hơn.

## 5. Quan hệ giữa `requires`, `exports` và quá trình phân giải mô-đun

Ba khái niệm này có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| `requires B;` | Mô-đun hiện tại đọc được mô-đun B và có thể dùng các package B cho phép truy cập. |
| `exports p;` | Mô-đun sở hữu package p công khai package đó cho mọi mô-đun đọc được nó. |
| `exports p to C;` | Công khai package p cho mô-đun C được chỉ định. |
| `public` | Cho phép truy cập kiểu hoặc thành viên theo quy tắc truy cập Java, sau khi các điều kiện ở cấp mô-đun/package đã được thỏa mãn. |

Khi khởi chạy:

```bash
java --module-path out -m com.acme.checkout/com.acme.checkout.Main
```

`com.acme.checkout` là mô-đun gốc được chọn để chạy. Quá trình phân giải tìm các mô-đun cần thiết theo các quan hệ `requires`; `com.acme.billing` được đưa vào đồ thị vì checkout yêu cầu nó.

Chỉ thị `exports` không tự thêm mô-đun vào đồ thị và cũng không thay thế `requires`. Nó chỉ quyết định package nào có thể được truy cập sau khi quan hệ đọc mô-đun đã tồn tại.

Một trường hợp đáng chú ý là API của mô-đun A công khai kiểu được định nghĩa trong mô-đun B, chẳng hạn kiểu B xuất hiện trong kiểu trả về hoặc tham số của phương thức public. Nếu consumer của A cũng cần đọc B để dùng API đó, A có thể khai báo:

```java
module com.acme.billing {
    requires transitive com.acme.money;
    exports com.acme.billing.api;
}
```

`requires transitive` truyền khả năng đọc mô-đun B tới các mô-đun phụ thuộc vào A. Nó là cơ chế về khả năng đọc trong đồ thị mô-đun, khác với `exports` vốn công khai package của chính mô-đun.

## 6. Phân biệt `exports` với `opens`

Hai chỉ thị đều liên quan đến ranh giới package nhưng phục vụ các mục đích khác nhau:

- `exports` công khai API để mã Java ở mô-đun khác có thể biên dịch và gọi các kiểu, thành viên được phép truy cập.
- `opens` cho phép truy cập phản chiếu ở runtime vào package, bao gồm deep reflection khi framework cần truy cập thành viên không public.
- `exports` không tự cho phép framework dùng reflection để mở private field hoặc private constructor.
- `opens` không làm cho package có thể được import như API Java ở thời điểm biên dịch.

Vì vậy, nếu mục tiêu là để consumer viết `import com.acme.billing.api.Invoice;`, hãy export package. Nếu mục tiêu là cho framework đọc hoặc thay đổi private state bằng reflection, hãy xem xét opens với phạm vi tối thiểu cần thiết. Không dùng `opens` thay cho `exports`.

## 7. Lỗi thường gặp và cách chẩn đoán

**Class public nhưng consumer không import được**

Kiểm tra package khai báo trong file Java có đúng với package được export trong `module-info.java` không. Sau đó kiểm tra consumer có `requires` đúng tên mô-đun cung cấp không.

**Đã khai báo `requires` nhưng package vẫn không truy cập được**

`requires` chỉ thiết lập khả năng đọc. Package vẫn phải được export cho consumer; nếu dùng qualified export thì tên consumer phải nằm trong danh sách `to`.

**Export package cha nhưng không dùng được package con**

Mỗi package là một đơn vị riêng. Export `com.acme.billing.api` không tự export `com.acme.billing.api.internal`.

**Import được class nhưng không gọi được constructor hoặc phương thức**

Kiểm tra modifier của thành viên và các kiểu xuất hiện trong chữ ký phương thức. Export package không thay đổi modifier của class hoặc thành viên.

**API public để lộ kiểu nội bộ**

Tránh để phương thức public trong package được export nhận hoặc trả về kiểu thuộc package không export nếu consumer cần thao tác với kiểu đó. Thiết kế kiểu public và chữ ký API sao cho consumer có thể sử dụng chúng mà không phụ thuộc vào chi tiết triển khai bị che.

**Nhầm qualified exports với `requires transitive`**

Qualified exports giới hạn mô-đun nào được truy cập một package. `requires transitive` truyền khả năng đọc một mô-đun phụ thuộc tới các consumer. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 8. Checklist khi thiết kế API mô-đun

Trước khi công khai một kiểu cho mô-đun khác, hãy kiểm tra:

1. Kiểu cần dùng nằm trong package nào và package đó đã được export chưa?
2. Consumer có `requires` mô-đun cung cấp chưa?
3. Nếu dùng qualified export, tên consumer đã được liệt kê chưa?
4. Kiểu, constructor, phương thức và các kiểu trong chữ ký API có thể truy cập theo quy tắc Java không?
5. Các package nội bộ và package con có được giữ ngoài API nếu consumer không cần chúng không?
6. Nếu API công khai kiểu từ một mô-đun phụ thuộc, có cần `requires transitive` để consumer đọc được mô-đun đó không?
7. Nhu cầu thực sự là gọi API public hay deep reflection? Chọn `exports` hoặc `opens` tương ứng.

Thiết kế package được export như hợp đồng công khai của mô-đun. Giữ package triển khai ở trạng thái không export giúp module duy trì quyền tự do thay đổi nội bộ mà không buộc các consumer phụ thuộc vào chi tiết không ổn định.
