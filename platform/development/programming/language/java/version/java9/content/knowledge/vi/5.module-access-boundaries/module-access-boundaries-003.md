# Package nội bộ và quan hệ giữa các package con

Trong Java, package giúp nhóm các kiểu liên quan, quản lý tên và xác định phạm vi truy cập package-private. Trong JPMS, một module có thể chứa nhiều package: package API được công bố cho module khác, còn package nội bộ giữ class triển khai và helper ở bên trong. Các package có tên dạng `com.acme.catalog.internal.validation` và `com.acme.catalog.internal` là hai package độc lập; package con theo cách đặt tên không tự động kế thừa quyền truy cập của package cha.

Thiết kế đúng ranh giới package giúp mã dễ tìm, giảm phụ thuộc giữa các phần và giữ chi tiết triển khai khỏi API công khai. Bài học này tập trung vào package nội bộ, quan hệ giữa package và subpackage, phạm vi truy cập trong Java và cách tổ chức chúng trong một named module hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt package, subpackage và module.
- Giải thích chính xác phạm vi package-private và vì sao subpackage không được xem là cùng package.
- Phân biệt package nội bộ với kiểu hoặc thành viên package-private.
- Hiểu quan hệ giữa package không export và các package được export trong cùng module.
- Tổ chức package API, internal, validation, storage và mapping theo trách nhiệm.
- Thiết kế facade để module bên ngoài chỉ phụ thuộc vào hợp đồng công khai.
- Biên dịch và chạy ví dụ nhiều package trong một named module Java 17+.

## 1. Package trong Java là gì?

Package là một namespace đặt tên cho các kiểu Java. Một file nguồn khai báo package ở đầu file bằng câu lệnh `package`:

~~~java
package com.acme.catalog.api;

public interface ProductCatalog {
}
~~~

Tên package thường viết chữ thường và dùng tên miền đảo ngược để giảm xung đột giữa các thư viện, ví dụ `com.acme.catalog.api`. Cấu trúc thư mục thường phản ánh tên package: package trên nằm trong thư mục `com/acme/catalog/api`.

Package có ba vai trò quan trọng:

1. **Tổ chức kiểu:** nhóm class, interface, enum, record và annotation theo chủ đề.
2. **Quản lý tên:** cho phép các kiểu cùng tên tồn tại trong những package khác nhau.
3. **Phạm vi truy cập:** kiểu cấp cao nhất và thành viên không có modifier truy cập có phạm vi package-private.

Package là khái niệm của ngôn ngữ Java. Module là đơn vị lớn hơn trong JPMS, chứa một hoặc nhiều package và khai báo package nào được công bố ra bên ngoài.

### 1.1. Câu lệnh package xác định package thực tế

Tên thư mục là quy ước tổ chức source tree; câu lệnh `package` trong file mới xác định package mà kiểu thuộc về. Khi cấu hình build, thư mục nguồn cần được ánh xạ nhất quán để compiler tìm đúng file.

Mỗi file nguồn chỉ có một khai báo package ở đầu file. Các file cùng khai báo một tên package thuộc cùng package nếu được biên dịch trong cùng môi trường module/class loader phù hợp. Trong named module, một package có một module sở hữu; không nên chia cùng một package giữa nhiều named module.

### 1.2. Package không phải thư mục cha có quyền bao trùm

Tên package có thể có các đoạn phân cấp:

~~~text
com.acme.catalog
com.acme.catalog.api
com.acme.catalog.internal
com.acme.catalog.internal.storage
com.acme.catalog.internal.validation
~~~

Các tên này tạo thành những package riêng biệt. `com.acme.catalog.internal.validation` không phải cùng package với `com.acme.catalog.internal`; nó chỉ có tiền tố tên giống nhau.

Do đó:

- Kiểu package-private trong `com.acme.catalog.internal` không truy cập được từ `com.acme.catalog.internal.validation`.
- Kiểu package-private trong `com.acme.catalog.internal.validation` không truy cập được từ `com.acme.catalog.internal.storage`.
- Wildcard import `import com.acme.catalog.internal.*;` chỉ áp dụng cho các kiểu trực tiếp trong package đó, không tự nhập kiểu trong các subpackage.
- Export package cha trong module descriptor không tự export các subpackage.

Đây là nguyên tắc quan trọng khi chia một package lớn thành các package con: việc tách tên và thư mục cũng tạo ra ranh giới truy cập package-private.

## 2. Phạm vi truy cập ở cấp package

Java có bốn mức truy cập cho thành viên: `private`, package-private (không ghi modifier), `protected` và `public`. Với kiểu cấp cao nhất, chỉ có thể dùng `public` hoặc package-private.

| Modifier | Ai có thể truy cập? | Mục đích thường gặp |
| --- | --- | --- |
| `private` | Bên trong lớp khai báo (bao gồm các quy tắc truy cập giữa các lớp lồng nhau cùng nest) | Ẩn trạng thái và chi tiết của một lớp |
| Không ghi modifier | Các kiểu trong cùng package | Chia sẻ helper giữa các lớp cùng package |
| `protected` | Cùng package và các lớp con theo quy tắc protected | Hỗ trợ mở rộng qua kế thừa |
| `public` | Mọi nơi được phép truy cập theo quy tắc package/module | API được công bố |

### 2.1. Package-private là gì?

Khi khai báo class hoặc thành viên mà không ghi `public`, `protected` hay `private`, mức truy cập mặc định là package-private:

~~~java
package com.acme.catalog.internal.validation;

final class ProductNameRules {
    static boolean isValid(String name) {
        return name != null && !name.isBlank();
    }
}
~~~

`ProductNameRules` chỉ được dùng trực tiếp bởi các kiểu trong package `com.acme.catalog.internal.validation`. Một class ở package `com.acme.catalog.internal` hoặc `com.acme.catalog.internal.storage` không thể import và gọi nó, dù các package đều nằm trong cùng một module.

Package-private hữu ích khi nhiều class cùng package cần chia sẻ một helper hoặc chi tiết triển khai, nhưng không muốn biến helper đó thành API public. Nó cũng giúp compiler phát hiện việc truy cập vượt khỏi ranh giới dự kiến.

### 2.2. Thành viên package-private

Một class public có thể giữ constructor, field hoặc method package-private:

~~~java
package com.acme.catalog.internal.validation;

public final class ProductNameValidator {
    public static boolean isValid(String name) {
        return ProductNameRules.isValid(name);
    }

    static String normalize(String name) {
        return name == null ? "" : name.trim();
    }
}
~~~

Các class trong cùng package có thể gọi `normalize`; class ở package khác chỉ gọi được phần public nếu có quyền truy cập vào package chứa class đó. Thành viên package-private không trở thành public chỉ vì class bao ngoài được khai báo public.

### 2.3. protected không phải là package-private mở rộng đơn giản

`protected` cho phép truy cập trong cùng package và cho phép lớp con ở package khác truy cập theo quy tắc kế thừa của Java. Khi truy cập từ package khác, có những giới hạn về kiểu tham chiếu và quan hệ subclass.

Không nên dùng `protected` chỉ để một package anh em gọi được helper. Nếu hai package cần hợp tác, hãy cân nhắc một API public nội bộ có trách nhiệm rõ, đặt các class cần chia sẻ trong cùng package, hoặc thiết kế một abstraction phù hợp.

### 2.4. Kiểu cấp cao nhất và nested type

Một top-level class hoặc interface có thể là `public` hoặc package-private. Nếu một kiểu chỉ phục vụ nội bộ package, hãy cân nhắc để package-private. Nếu cần tổ chức một kiểu phụ bên trong class khác, có thể dùng nested class với modifier phù hợp.

Không cần biến mọi class thành public. Public rộng hơn mức cần thiết sẽ làm các phần khác phụ thuộc vào chi tiết triển khai và khiến việc đổi cấu trúc khó hơn.

## 3. Package nội bộ và package được công bố trong JPMS

### 3.1. Package nội bộ là quy ước kiến trúc

Tên như `internal`, `impl`, `storage`, `validation` hoặc `mapping` thường được dùng để biểu thị package triển khai. Các từ này không phải keyword đặc biệt của Java. Compiler không tự bảo vệ package chỉ vì tên của nó có chữ `internal`.

Trong named module, cơ chế bảo vệ ở cấp module đến từ việc không export package đó. Ví dụ:

~~~java
module catalog.core {
    exports com.acme.catalog.api;
}
~~~

Module `catalog.core` công bố package `com.acme.catalog.api`. Các package `com.acme.catalog.internal`, `com.acme.catalog.internal.storage` và `com.acme.catalog.internal.validation` vẫn nằm trong module nhưng không được công bố cho module khác truy cập theo cách thông thường.

### 3.2. exports chỉ áp dụng cho package được nêu

JPMS không hiểu `exports com.acme.catalog.internal.*;` như một mẫu wildcard để xuất toàn bộ cây package. Mỗi directive `exports` chỉ áp dụng cho đúng package được ghi.

Ví dụ:

~~~java
module catalog.core {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
}
~~~

Hai package được công bố là `com.acme.catalog.api` và `com.acme.catalog.spi`. Các package con hoặc package khác không tự được export.

Điều này cho phép module có một package API nhỏ và nhiều package triển khai. Các package nội bộ vẫn có thể dùng public class của nhau trong cùng module nếu package và kiểu cho phép; chúng không cần export chỉ để giao tiếp nội bộ.

### 3.3. public trong package không export vẫn là nội bộ đối với module khác

Một class có modifier `public` trong package không export vẫn có thể được sử dụng bởi các package khác bên trong module theo quy tắc Java. Nhưng một module khác không thể dùng class đó như API thông thường vì package không được export.

Cần phân biệt hai lớp kiểm soát:

- **Java access control:** private, package-private, protected và public.
- **JPMS access control:** module readability và package exports.

Một module khác có thể khai báo `requires catalog.core;` nhưng điều đó chỉ làm module trở nên đọc được. Nó không tự cấp quyền truy cập vào package nội bộ chưa export. Ngược lại, export một package không biến thành viên package-private thành public.

### 3.4. Package con không tự động được mở hoặc export theo package cha

Nếu module descriptor chỉ có:

~~~java
module catalog.core {
    exports com.acme.catalog.api;
}
~~~

thì `com.acme.catalog.api.dto` vẫn không được export. Nếu thật sự cần công bố package con đó, phải thêm directive riêng:

~~~java
module catalog.core {
    exports com.acme.catalog.api;
    exports com.acme.catalog.api.dto;
}
~~~

Hãy cân nhắc trước khi export nhiều package con: mỗi package công khai làm tăng bề mặt API mà module cần duy trì. Có thể thay nhiều package export bằng một package API có facade hoặc kiểu dữ liệu phù hợp nếu điều đó làm hợp đồng dễ hiểu hơn.

### 3.5. opens cũng có phạm vi package cụ thể

Nếu một framework cần reflection sâu vào package nội bộ, module có thể khai báo `opens` cho đúng package và module đích. Việc mở một package không tự mở các subpackage của nó. Mỗi package cần reflection phải được mở rõ ràng hoặc nằm trong một open module theo thiết kế phù hợp.

`opens` phục vụ deep reflection; nó không công bố API thông thường và không thay thế `exports`.

## 4. Quan hệ giữa package cha và package con

### 4.1. Quan hệ tên không tạo quan hệ truy cập

Hãy xem:

~~~text
com.acme.catalog.internal
com.acme.catalog.internal.storage
com.acme.catalog.internal.validation
~~~

Các package này có thể cùng thuộc module `catalog.core`, nhưng mỗi package có phạm vi package-private riêng. Một class trong `internal.storage` không tự động truy cập được package-private type trong `internal.validation`.

Nếu cần chia sẻ một helper giữa hai package, hãy quyết định rõ ranh giới:

- Nếu helper chỉ phục vụ một nhóm class nhỏ, đặt chúng trong cùng package.
- Nếu helper cần được dùng qua nhiều package, công bố một kiểu hoặc method public có mục đích rõ trong module nội bộ.
- Nếu hai phần có trách nhiệm khác nhau, tạo abstraction hoặc API nhỏ thay vì truy cập trực tiếp vào chi tiết bên trong nhau.
- Nếu nhiều package thường xuyên phải dùng chung phần lớn implementation, có thể ranh giới package đang bị chia quá nhỏ.

### 4.2. Wildcard import không đệ quy

Lệnh:

~~~java
import com.acme.catalog.internal.*;
~~~

chỉ cho phép tham chiếu các kiểu cấp cao nhất trong package `com.acme.catalog.internal`. Nó không nhập các kiểu trong `com.acme.catalog.internal.storage` hoặc `com.acme.catalog.internal.validation`.

Khi dùng kiểu ở package con, phải import đúng package:

~~~java
import com.acme.catalog.internal.storage.InMemoryProductRepository;
~~~

Wildcard import không thay đổi phạm vi truy cập. Nó không làm class package-private trở nên truy cập được và không vượt qua giới hạn exports của JPMS.

### 4.3. Tránh split package

Split package là tình huống cùng một package name bị phân chia giữa nhiều module. Trong module graph của JPMS, hãy giữ mỗi package có một module sở hữu rõ ràng; không chia các class cùng package giữa nhiều named module.

Khi tách module từ một codebase cũ, hãy chuyển toàn bộ package sang module sở hữu phù hợp và điều chỉnh dependency. Đặt các class vào những subpackage riêng là một cách phân tách namespace, nhưng vẫn cần kiểm tra rằng chúng có API và trách nhiệm phù hợp.

## 5. Cách tổ chức package nội bộ theo trách nhiệm

Một module catalog có thể có cấu trúc:

~~~text
catalog.core
├── com.acme.catalog.api
│   ├── ProductCatalog.java
│   └── Catalogs.java
└── com.acme.catalog.internal
    ├── CatalogEngine.java
    ├── storage
    │   └── InMemoryProductRepository.java
    └── validation
        ├── ProductNameValidator.java
        └── ProductNameRules.java
~~~

Một cách phân chia thường gặp:

| Package | Trách nhiệm | Phạm vi gợi ý |
| --- | --- | --- |
| `api` | Hợp đồng và kiểu dữ liệu cho bên sử dụng | Export nếu module khác cần |
| `internal` | Điều phối và triển khai nội bộ | Không export |
| `internal.storage` | Truy cập và lưu trữ dữ liệu | Không export |
| `internal.validation` | Quy tắc kiểm tra nội bộ | Không export |
| `internal.mapping` | Chuyển đổi dữ liệu giữa các mô hình nội bộ | Không export |
| `spi` | Hợp đồng mở rộng cho provider bên ngoài | Export khi thật sự cần |

Tên package chỉ là một phần của thiết kế. Hãy xác định trách nhiệm và hợp đồng trước, sau đó mới quyết định package nào nên chứa class nào.

### 5.1. Package api

Package API chứa kiểu mà module khác cần tham chiếu. Nên giữ nó ổn định và tránh phụ thuộc vào class triển khai.

Ví dụ, `ProductCatalog` mô tả thao tác tìm sản phẩm. Bên sử dụng không cần biết catalog lấy dữ liệu từ bộ nhớ hay database.

### 5.2. Package internal

Package internal có thể chứa facade triển khai, engine hoặc coordinator. Nếu chỉ được sử dụng trong module, các class có thể public để package nội bộ khác gọi, nhưng không cần export package đó.

Public trong package không export không đồng nghĩa với public API của hệ thống. Đây là cách giữ quyền sử dụng nội bộ trong module mà không công bố class ra ngoài.

### 5.3. Các subpackage theo trách nhiệm

Các package như storage, validation, mapping nên được tách khi chúng có trách nhiệm rõ và có đủ nội dung để tạo thành một nhóm dễ quản lý. Không tạo một subpackage cho từng class hoặc chỉ vì tên thư mục trông có vẻ gọn.

Nếu các class trong nhiều package thường xuyên truy cập helper nội bộ của nhau, hãy xem lại ranh giới. Có thể nhóm chúng vào cùng package, hoặc thay sự phụ thuộc trực tiếp bằng một API nội bộ nhỏ.

### 5.4. Package-info.java

File `package-info.java` có thể dùng để đặt Javadoc hoặc annotation ở cấp package. Ví dụ:

~~~java
/**
 * Internal validation rules for catalog data.
 * This package is not part of the exported module API.
 */
package com.acme.catalog.internal.validation;
~~~

Nó hữu ích để ghi mục đích và quy ước của package, đặc biệt khi module có nhiều nhóm package nội bộ. Đây là tài liệu cho người phát triển; bản thân comment không tạo ra ranh giới truy cập.

## 6. Ví dụ chạy được: API công khai và các package nội bộ

Ví dụ dưới đây dùng hai module:

- `catalog.core`: export duy nhất package API; giữ engine, storage và validation bên trong.
- `catalog.app`: chỉ sử dụng facade và interface trong package API.

Cấu trúc source:

~~~text
src/
├── catalog.core/
│   ├── module-info.java
│   └── com/acme/catalog/
│       ├── api/
│       │   ├── ProductCatalog.java
│       │   └── Catalogs.java
│       └── internal/
│           ├── CatalogEngine.java
│           ├── storage/
│           │   └── InMemoryProductRepository.java
│           └── validation/
│               ├── ProductNameValidator.java
│               └── ProductNameRules.java
└── catalog.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

### 6.1. Module descriptor

File `src/catalog.core/module-info.java`:

~~~java
module catalog.core {
    exports com.acme.catalog.api;
}
~~~

Chỉ package `com.acme.catalog.api` được export. Các package internal và subpackage của nó không tự được công bố.

File `src/catalog.app/module-info.java`:

~~~java
module catalog.app {
    requires catalog.core;
}
~~~

Ứng dụng đọc module core và chỉ truy cập được API mà core export.

### 6.2. Hợp đồng API

File `src/catalog.core/com/acme/catalog/api/ProductCatalog.java`:

~~~java
package com.acme.catalog.api;

import java.util.List;

public interface ProductCatalog {
    List<String> listNames();
}
~~~

File `src/catalog.core/com/acme/catalog/api/Catalogs.java`:

~~~java
package com.acme.catalog.api;

import com.acme.catalog.internal.CatalogEngine;

public final class Catalogs {
    private Catalogs() { }

    public static ProductCatalog createDefault() {
        return new CatalogEngine();
    }
}
~~~

Bên ngoài chỉ cần biết `ProductCatalog` và `Catalogs`. Factory trả về interface API thay vì để bên sử dụng phụ thuộc vào `CatalogEngine`.

### 6.3. Engine trong package internal

File `src/catalog.core/com/acme/catalog/internal/CatalogEngine.java`:

~~~java
package com.acme.catalog.internal;

import com.acme.catalog.api.ProductCatalog;
import com.acme.catalog.internal.storage.InMemoryProductRepository;
import com.acme.catalog.internal.validation.ProductNameValidator;
import java.util.List;

public final class CatalogEngine implements ProductCatalog {
    private final InMemoryProductRepository repository =
            new InMemoryProductRepository();

    @Override
    public List<String> listNames() {
        return repository.loadNames().stream()
                .filter(ProductNameValidator::isValid)
                .toList();
    }
}
~~~

Engine có thể dùng public class trong các package nội bộ cùng module. Nó không cần export package internal để các package khác trong module sử dụng.

### 6.4. Package storage

File `src/catalog.core/com/acme/catalog/internal/storage/InMemoryProductRepository.java`:

~~~java
package com.acme.catalog.internal.storage;

import java.util.List;

public final class InMemoryProductRepository {
    public List<String> loadNames() {
        return List.of("Keyboard", "Mouse", "", "Monitor");
    }
}
~~~

Repository là public để `CatalogEngine` ở package khác có thể gọi. Package storage vẫn không được export, vì vậy ứng dụng bên ngoài không thể import class này như API thông thường.

### 6.5. Package validation và helper package-private

File `src/catalog.core/com/acme/catalog/internal/validation/ProductNameValidator.java`:

~~~java
package com.acme.catalog.internal.validation;

public final class ProductNameValidator {
    private ProductNameValidator() { }

    public static boolean isValid(String name) {
        return ProductNameRules.isValid(name);
    }
}
~~~

File `src/catalog.core/com/acme/catalog/internal/validation/ProductNameRules.java`:

~~~java
package com.acme.catalog.internal.validation;

final class ProductNameRules {
    private ProductNameRules() { }

    static boolean isValid(String name) {
        return name != null && !name.isBlank() && name.length() <= 40;
    }
}
~~~

`ProductNameRules` và method `isValid` là package-private. Chúng chỉ được sử dụng trong `com.acme.catalog.internal.validation`. Engine gọi qua `ProductNameValidator`, một API nội bộ public của package validation.

Nếu `CatalogEngine` cố import trực tiếp `ProductNameRules`, compiler sẽ từ chối vì engine thuộc package khác. Cùng module không có nghĩa là mọi package chia sẻ quyền package-private.

### 6.6. Ứng dụng bên ngoài

File `src/catalog.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.catalog.api.Catalogs;
import com.acme.catalog.api.ProductCatalog;

public final class Main {
    public static void main(String[] args) {
        ProductCatalog catalog = Catalogs.createDefault();
        System.out.println("products=" + catalog.listNames());
    }
}
~~~

Ứng dụng không import `CatalogEngine`, `InMemoryProductRepository` hoặc `ProductNameValidator`. Nó chỉ dùng hợp đồng trong package API.

### 6.7. Biên dịch và chạy

Từ thư mục chứa `src`, dùng JDK 17 trở lên:

~~~bash
javac --release 17 --module-source-path src -d out -m catalog.core,catalog.app
java --module-path out -m catalog.app/com.acme.app.Main
~~~

Kết quả stdout:

~~~text
products=[Keyboard, Mouse, Monitor]
~~~

Kết quả cho thấy package validation đã lọc chuỗi rỗng, các package nội bộ hợp tác trong cùng module, và ứng dụng chỉ sử dụng package API được export.

## 7. Cách kiểm tra ranh giới package

Khi xem xét một package, hãy kiểm tra theo các câu hỏi sau:

1. Class trong package có cùng trách nhiệm và thường thay đổi cùng nhau không?
2. Kiểu nào cần public để package khác sử dụng?
3. Kiểu nào có thể package-private vì chỉ phục vụ class cùng package?
4. Package này có cần được module khác truy cập hay chỉ được dùng nội bộ?
5. Nếu package có subpackage, các subpackage có trách nhiệm độc lập hay chỉ đang tách tên tùy tiện?
6. Package nào cần export trong module descriptor?
7. Có package nào bị chia giữa nhiều named module không?
8. Một thay đổi nội bộ có buộc bên sử dụng sửa import hoặc gọi class triển khai không?

Có thể kiểm tra module descriptor sau khi biên dịch bằng:

~~~bash
java --module-path out --describe-module catalog.core
~~~

Lệnh hiển thị tên module và các directive đã biên dịch. Nó giúp xác nhận package nào được export và các quan hệ module được khai báo. Để kiểm tra truy cập package-private, hãy biên dịch một đoạn mã từ package khác thử gọi kiểu hoặc thành viên đó; compiler phải báo lỗi nếu ranh giới được thiết kế đúng.

## 8. Lỗi thiết kế thường gặp

- **Cho rằng subpackage được thừa kế quyền package-private:** subpackage là package riêng; hãy dùng API nội bộ public hoặc tổ chức lại package khi cần chia sẻ.
- **Export package cha và nghĩ package con cũng được export:** mỗi package cần directive riêng nếu phải công bố.
- **Cho rằng public class trong package internal tự động là API:** nếu package không export, module khác không thể truy cập class đó theo cách thông thường.
- **Dùng wildcard import để nhập cả cây package:** wildcard không đệ quy và không vượt qua access control.
- **Để mọi class đều public:** public không cần thiết làm lộ thêm chi tiết và tăng phụ thuộc.
- **Tạo quá nhiều subpackage nhỏ:** package nên phản ánh trách nhiệm, không chỉ phản ánh số class.
- **Để package khác gọi trực tiếp helper package-private bằng cách đổi modifier liên tục:** nếu cần chia sẻ, hãy thiết kế API nội bộ có chủ đích.
- **Chia cùng package giữa nhiều named module:** giữ một module sở hữu package và tránh split package.
- **Đặt tên internal nhưng lại export package:** tên gọi không tạo ra bảo vệ; cần kiểm tra module descriptor.
- **Dùng opens thay cho exports:** opens dành cho reflection sâu, không công bố API thông thường.

## 9. Checklist tự đánh giá

- [ ] Giải thích được package khác module như thế nào.
- [ ] Biết rằng package con là package độc lập, không có quyền package-private của package cha.
- [ ] Phân biệt được package-private class và public class.
- [ ] Biết phạm vi của private, package-private, protected và public.
- [ ] Hiểu wildcard import không nhập các subpackage.
- [ ] Biết exports trong module descriptor chỉ áp dụng cho package được nêu.
- [ ] Hiểu rằng requires không làm package nội bộ tự trở thành API.
- [ ] Tổ chức được package api và các package internal theo trách nhiệm.
- [ ] Biết dùng facade/interface để che giấu engine và repository.
- [ ] Nhận diện và tránh split package trong named module.
- [ ] Biết kiểm tra module descriptor và thử biên dịch để xác nhận access boundary.
