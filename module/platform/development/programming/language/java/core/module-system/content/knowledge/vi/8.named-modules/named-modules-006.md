# Named module và package uniqueness

Trong Java Platform Module System (JPMS), một named module sở hữu một tập hợp package. Khi nhiều named module được resolve cùng trong một module configuration, quy tắc package uniqueness giúp xác định rõ package thuộc về module nào. Vì vậy, việc chia cùng một package giữa nhiều named module (split package) là nguồn gây xung đột khi biên dịch hoặc resolve module.

Quy tắc này khác với cách tổ chức JAR truyền thống trên classpath, nơi nhiều JAR có thể đóng góp class vào cùng một package của unnamed module. Khi chuyển ứng dụng sang module path, cấu trúc package cần được thiết kế lại để mỗi package có một chủ sở hữu rõ ràng.

## 1. Module và package là hai cấp tổ chức khác nhau

Một **package** nhóm các kiểu Java có liên quan, ví dụ:

    com.example.billing.api
    com.example.billing.internal

Một **module** gom nhiều package thành một đơn vị có tên, phụ thuộc và ranh giới truy cập được khai báo trong `module-info.java`.

Ví dụ:

    module com.example.billing {
        requires com.example.shared;
        exports com.example.billing.api;
    }

Module `com.example.billing` có thể sở hữu nhiều package. Directive `exports` chỉ định package được module khác truy cập theo quy tắc Java thông thường; nó không tạo package và cũng không chuyển quyền sở hữu package sang module khác.

Tên module và tên package thuộc hai không gian tên riêng. Một module có thể tên `com.example.billing`, trong khi các package bên trong có tên `com.example.billing.api` hoặc `com.example.billing.internal`.

## 2. Package uniqueness trong named modules

Trong cùng một module configuration, một package chỉ có một chủ sở hữu là một named module. Không thể chia các class thuộc cùng package giữa hai named module cùng được resolve trong configuration đó.

Ví dụ, module A có:

    package com.example.shared.util;

    public final class MoneyFormatter {
    }

Trong khi module B cũng có:

    package com.example.shared.util;

    public final class DateFormatter {
    }

Dù hai module không chứa class trùng tên, chúng vẫn cùng khai báo package `com.example.shared.util`. Đây là **split package**: một package bị phân tán qua nhiều module.

JPMS yêu cầu package có một chủ sở hữu rõ ràng trong module configuration. Vì thế, việc đưa cả hai named module chứa package này vào cùng cấu hình có thể bị từ chối trong quá trình biên dịch hoặc resolve module.

Điểm quan trọng: split package không chỉ là hai JAR chứa một class có cùng tên đầy đủ. Chỉ cần hai module cùng chứa các class khác nhau nhưng khai báo cùng một package, xung đột package đã xuất hiện.

## 3. Ví dụ cấu trúc split package

Giả sử có hai module:

    src/
    ├── com.example.billing/
    │   ├── module-info.java
    │   └── com/example/shared/util/MoneyFormatter.java
    └── com.example.reporting/
        ├── module-info.java
        └── com/example/shared/util/DateFormatter.java

Module billing:

    module com.example.billing {
        exports com.example.shared.util;
    }

File `MoneyFormatter.java`:

    package com.example.shared.util;

    public final class MoneyFormatter {
        public static String format(long amount) {
            return amount + " VND";
        }
    }

Module reporting:

    module com.example.reporting {
        exports com.example.shared.util;
    }

File `DateFormatter.java`:

    package com.example.shared.util;

    public final class DateFormatter {
        public static String format(int year) {
            return "Year " + year;
        }
    }

Hai module đều khai báo và export `com.example.shared.util`. Khi cùng được biên dịch hoặc resolve, module system không thể coi package đó thuộc về cả hai module.

Có thể thử biên dịch từ thư mục chứa `src`:

    javac --module-source-path src -d out
        -m com.example.billing,com.example.reporting

Trình biên dịch sẽ báo lỗi liên quan đến package đã tồn tại trong module khác hoặc package bị chia giữa các module. Thông báo cụ thể có thể khác theo phiên bản JDK và cách tổ chức module source path.

Việc đổi tên module không giải quyết được vấn đề. Hai module vẫn sở hữu cùng package name `com.example.shared.util`.

## 4. Cách sửa: chuyển package dùng chung vào một module

Nếu `MoneyFormatter` và `DateFormatter` thực sự thuộc về cùng một nhóm tiện ích dùng chung, hãy tạo module riêng sở hữu package đó.

Cấu trúc sau khi sửa:

    src/
    ├── com.example.shared/
    │   ├── module-info.java
    │   └── com/example/shared/util/
    │       ├── MoneyFormatter.java
    │       └── DateFormatter.java
    ├── com.example.billing/
    │   └── module-info.java
    └── com.example.reporting/
        └── module-info.java

Module shared:

    module com.example.shared {
        exports com.example.shared.util;
    }

Module billing:

    module com.example.billing {
        requires com.example.shared;
    }

Module reporting:

    module com.example.reporting {
        requires com.example.shared;
    }

Bây giờ package `com.example.shared.util` chỉ thuộc về module `com.example.shared`. Hai module billing và reporting đều đọc module shared để sử dụng các kiểu public được export.

Biên dịch:

    javac --module-source-path src -d out
        -m com.example.shared,com.example.billing,com.example.reporting

Cách này thể hiện rõ quyền sở hữu: module shared chịu trách nhiệm về các kiểu tiện ích, còn module billing và reporting chỉ là các module tiêu thụ.

## 5. Cách sửa khác: tách package theo trách nhiệm

Không phải mọi class trùng package đều thực sự là thành phần dùng chung. Nếu chúng thuộc các miền nghiệp vụ khác nhau, có thể đặt chúng vào package riêng:

    com.example.billing.internal
    com.example.reporting.internal

Ví dụ, module billing sở hữu:

    package com.example.billing.internal;

    public final class MoneyFormatter {
    }

Module reporting sở hữu:

    package com.example.reporting.internal;

    public final class DateFormatter {
    }

Hai package này khác nhau nên có thể thuộc hai named module khác nhau trong cùng configuration.

Cách tách package thường phù hợp khi class chỉ phục vụ nội bộ cho một module. Không nên tạo module shared chỉ để gom các class không có quan hệ trách nhiệm hoặc không có nhu cầu được dùng chung.

## 6. Package con không phải cùng một package

Tên package trong Java có dạng phân cấp theo quy ước đặt tên, nhưng mỗi tên đầy đủ vẫn đại diện cho một package riêng.

Ví dụ:

- `com.example.billing`
- `com.example.billing.api`
- `com.example.billing.internal`

Đây là ba package khác nhau. Vì vậy, `com.example.billing` có thể thuộc một module trong khi `com.example.billing.api` thuộc module khác, nếu cấu trúc được thiết kế như vậy và không có package name trùng nhau.

Tương tự, export một package không tự động export các package con:

    module com.example.billing {
        exports com.example.billing;
    }

Directive trên không export `com.example.billing.api`. Nếu muốn module khác truy cập kiểu public trong package con đó, cần khai báo riêng:

    module com.example.billing {
        exports com.example.billing;
        exports com.example.billing.api;
    }

Quy tắc package uniqueness xét tên package đầy đủ. Việc hai package có chung tiền tố không tự tạo split package.

## 7. Quan hệ giữa package uniqueness và exports

`exports` và package ownership giải quyết hai câu hỏi khác nhau:

- **Package ownership:** package thuộc về named module nào trong configuration?
- **Exports:** module sở hữu package cho module khác truy cập kiểu public trong package đó hay không?

Ví dụ:

    module com.example.internal {
        // package com.example.internal.impl tồn tại trong module
    }

Package có thể thuộc module dù không được export. Module khác không thể import kiểu trong package chưa export, nhưng điều đó không làm package mất quyền sở hữu của module.

Ngược lại, hai module cùng export một package không thể cùng làm chủ package đó trong một module configuration. Việc thêm `exports`, `opens` hay `requires transitive` không phải cách sửa split package; cần sửa cấu trúc package và module sở hữu.

## 8. Classpath và module path khác nhau như thế nào?

Trước JPMS, ứng dụng thường đặt nhiều JAR trên classpath. Các class trên classpath được gom vào unnamed module của class loader tương ứng. Vì vậy, nhiều JAR có thể đóng góp các class khác nhau vào cùng package.

Ví dụ:

    legacy-a.jar
      com.example.shared.util.MoneyFormatter

    legacy-b.jar
      com.example.shared.util.DateFormatter

Khi cả hai JAR nằm trên classpath, chúng có thể cùng đóng góp class vào package `com.example.shared.util` của unnamed module.

Khi chuyển mỗi JAR thành một named module riêng trên module path, package này sẽ bị chia giữa các named module. Cấu trúc vốn hoạt động trên classpath có thể không còn hợp lệ khi resolve thành named modules.

Đây là lý do cần kiểm kê package trước khi modularize một hệ thống cũ. Đừng chỉ thêm `module-info.java` vào từng JAR mà bỏ qua package đang được chia sẻ giữa các artifact.

## 9. Automatic module cũng chịu quy tắc module path

Một JAR chưa có `module-info.class` khi đặt trên module path có thể trở thành **automatic module**. Tên module thường được suy ra từ tên JAR hoặc từ manifest nếu có khai báo `Automatic-Module-Name`.

Automatic module vẫn là một named module trong module configuration. Các package của nó được suy ra từ nội dung JAR; vì vậy, nó cũng có thể tham gia vào xung đột split package với một named module khác.

Ví dụ, nếu `legacy-util.jar` trở thành automatic module `legacy.util` và chứa package `com.example.shared.util`, trong khi `com.example.shared` cũng chứa package đó, việc đưa cả hai vào cùng module configuration có thể gây xung đột.

Automatic module có một số quy tắc readability và exports rộng hơn explicit module, nhưng điều đó không có nghĩa nó được miễn các ràng buộc package của named-module configuration.

## 10. Cách kiểm tra khi gặp lỗi package

Khi module build hoặc runtime báo lỗi package bị trùng, hãy kiểm tra theo thứ tự:

1. Xác định package name đầy đủ trong thông báo lỗi, ví dụ `com.example.shared.util`.
2. Xác định các module hoặc JAR đang chứa package đó.
3. Kiểm tra module nào nên sở hữu các class dùng chung.
4. Chuyển class dùng chung về một module hoặc đổi package của class chỉ phục vụ nội bộ.
5. Cập nhật `requires` và `exports` theo quan hệ mới.
6. Biên dịch và resolve lại toàn bộ các module liên quan.

Có thể xem descriptor của một modular JAR:

    jar --describe-module --file libs/example.jar

Có thể liệt kê nội dung JAR để tìm package:

    jar --list --file libs/example.jar

Với JDK hỗ trợ tùy chọn kiểm tra module, có thể yêu cầu launcher xác thực module path:

    java --module-path mods --validate-modules

Nếu lỗi chỉ xuất hiện khi chuyển từ classpath sang module path, hãy kiểm tra các JAR phụ thuộc cũ và automatic modules trước. Một package có thể đã bị chia giữa nhiều artifact từ trước khi dự án áp dụng JPMS.

## 11. Những nhầm lẫn thường gặp

- **Tưởng hai class khác nhau thì không thể gây split package.** Chúng vẫn xung đột nếu cùng khai báo một package nhưng nằm trong hai named module.
- **Tưởng chỉ cần đổi module name.** Tên module khác nhau không làm package name trở nên khác nhau.
- **Tưởng package con là một phần của package cha.** `com.example.api` và `com.example.api.internal` là hai package riêng.
- **Tưởng chỉ package được export mới được tính.** Package ownership không phụ thuộc việc package có được export hay không.
- **Tưởng automatic module được miễn package uniqueness.** Automatic module vẫn là named module trên module path.
- **Tưởng split package trên classpath chứng minh cấu trúc đó hợp lệ trên module path.** Classpath gom các JAR vào unnamed module; named modules có quy tắc ownership chặt chẽ hơn.
- **Tưởng `exports` hoặc `opens` giải quyết được split package.** Các directive này điều khiển quyền truy cập, không thay đổi module sở hữu package.

## Ghi nhớ

Trong cùng một module configuration, hãy thiết kế để mỗi package có một named module sở hữu rõ ràng. Nếu nhiều module cần dùng các class trong cùng package, chuyển package đó vào một module shared. Nếu các class chỉ thuộc nội bộ từng module, tách chúng thành các package riêng theo trách nhiệm.

Khi modularize một hệ thống cũ, hãy kiểm tra cả explicit modules lẫn automatic modules trên module path, vì split package thường chỉ bộc lộ sau khi các JAR được đưa vào named-module configuration.