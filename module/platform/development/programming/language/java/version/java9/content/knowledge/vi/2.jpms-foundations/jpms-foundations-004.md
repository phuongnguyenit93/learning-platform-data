# Khả năng đọc mô-đun và khả năng truy cập kiểu trong JPMS

## Mục tiêu

Trong Java Platform Module System (JPMS), một lớp được khai báo public chưa chắc đã dùng được từ mô-đun khác. Việc truy cập qua ranh giới mô-đun cần thỏa mãn hai nhóm điều kiện:

- **Readability (khả năng đọc mô-đun):** mô-đun gọi có đọc được mô-đun chứa kiểu cần dùng hay không.
- **Accessibility (khả năng truy cập):** package chứa kiểu có được xuất cho mô-đun gọi hay không, và kiểu/thành viên có thỏa quy tắc access modifier của Java hay không.

Readability được khai báo bằng requires; exports công khai package; public, protected, package-private và private tiếp tục kiểm soát quyền truy cập ở cấp ngôn ngữ. Khi cần framework truy cập sâu bằng reflection, opens có vai trò riêng ở runtime.

## 1. Điều kiện để sử dụng một kiểu từ mô-đun khác

Giả sử ứng dụng com.acme.app muốn sử dụng lớp Point thuộc mô-đun com.acme.geometry.

Mô-đun cung cấp:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

Mô-đun gọi:

~~~java
module com.acme.app {
    requires com.acme.geometry;
}
~~~

Kiểu API:

~~~java
package com.acme.geometry.api;

public final class Point {
    public Point(int x, int y) {}
}
~~~

Ứng dụng sử dụng được Point khi đồng thời thỏa ba điều kiện:

1. com.acme.app đọc được com.acme.geometry.
2. com.acme.geometry xuất package com.acme.geometry.api cho com.acme.app.
3. Point và constructor được gọi có quyền truy cập phù hợp theo quy tắc Java.

| Lớp kiểm soát | Cơ chế | Câu hỏi |
|---|---|---|
| Readability | requires và các biến thể | Mô-đun gọi có đọc được mô-đun cung cấp không? |
| Module accessibility | exports | Package có được công khai cho mô-đun gọi không? |
| Java accessibility | public, protected, package-private, private | Kiểu hoặc thành viên có được phép truy cập theo quy tắc ngôn ngữ không? |

requires không tự xuất package. exports cũng không tự tạo quan hệ readability từ mô-đun gọi đến mô-đun cung cấp. Cần cấu hình đúng cả hai phía.

## 2. Khả năng đọc mô-đun (readability)

Readability là quan hệ trong đồ thị mô-đun. Một mô-đun đọc được mô-đun khác khi quan hệ phụ thuộc được khai báo và mô-đun được phân giải thành công.

### requires: phụ thuộc trực tiếp

~~~java
module com.acme.app {
    requires com.acme.geometry;
    requires java.sql;
}
~~~

Khai báo requires cho biết mô-đun hiện tại cần đọc các mô-đun được liệt kê. Trình biên dịch dùng quan hệ này khi kiểm tra kiểu và API; module resolver dùng đồ thị phụ thuộc khi khởi chạy ứng dụng modular.

java.base được mọi mô-đun yêu cầu ngầm định, vì vậy thông thường không cần khai báo requires java.base.

### requires transitive: truyền khả năng đọc cho consumer

Giả sử API public của com.acme.geometry có kiểu thuộc com.acme.units trong chữ ký method. Consumer chỉ khai báo requires com.acme.geometry nhưng cũng cần đọc com.acme.units để sử dụng API đó.

Geometry có thể khai báo:

~~~java
module com.acme.geometry {
    requires transitive com.acme.units;
    exports com.acme.geometry.api;
}
~~~

Khi mô-đun khác yêu cầu com.acme.geometry, requires transitive làm cho consumer đó cũng đọc được com.acme.units.

Lưu ý:

- requires transitive truyền readability của dependency đến các mô-đun phụ thuộc vào mô-đun hiện tại.
- Nó không tự xuất package của dependency. com.acme.units vẫn phải exports package mà consumer cần sử dụng.
- Chỉ dùng transitive khi dependency là một phần của hợp đồng API mà người tiêu thụ cần đọc trực tiếp, chẳng hạn kiểu của dependency xuất hiện trong chữ ký public.

### requires static: dependency tùy chọn ở runtime

~~~java
module com.acme.geometry {
    requires static com.acme.annotations;
    exports com.acme.geometry.api;
}
~~~

requires static khai báo dependency cần có khi biên dịch nhưng có thể không cần hiện diện lúc chạy. Trường hợp phù hợp là annotation hoặc công cụ chỉ cần ở compile-time. Nếu logic thực thi thực sự gọi dependency đó, nó vẫn phải có mặt khi chạy; khi đó dùng requires thông thường.

### Readability không tự truyền qua mọi requires

Giả sử app khai báo requires service và service khai báo requires model. app đọc service nhưng không mặc nhiên đọc model chỉ vì service đọc model. Nếu kiểu của model xuất hiện trong API mà consumer cần dùng, service có thể cần khai báo requires transitive model.

Hãy chọn requires transitive dựa trên hợp đồng API, không dùng nó cho mọi dependency.

## 3. exports: công khai package

Một mô-đun có thể chứa nhiều package, nhưng chỉ package được xuất mới trở thành API có thể sử dụng từ mô-đun khác đọc mô-đun đó.

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

Package com.acme.geometry.api được xuất. Package com.acme.geometry.internal vẫn được giữ nội bộ nếu không có chỉ thị exports tương ứng. Điều này giúp thư viện thay đổi implementation mà ít ảnh hưởng đến consumer.

### Qualified exports

Có thể chỉ xuất package cho mô-đun được chỉ định:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.spi to com.acme.plugin;
}
~~~

Đây là qualified exports. com.acme.plugin được phép truy cập package com.acme.geometry.spi nếu nó đọc com.acme.geometry. Các mô-đun khác không được cấp quyền qua chỉ thị này.

Qualified exports hữu ích cho SPI hoặc hợp đồng giữa một số mô-đun được kiểm soát. Với API công khai rộng rãi, dùng exports thông thường.

### exports không biến mọi kiểu thành public

~~~java
package com.acme.geometry.api;

public class Point {
    public Point() {}

    public int x() {
        return 10;
    }

    int internalCode() {
        return 42;
    }
}
~~~

Nếu package đã được xuất, mô-đun bên ngoài có thể dùng lớp public Point, gọi constructor public và gọi x(). Nó vẫn không thể gọi internalCode() vì method này có package-private access.

JPMS quyết định package có thể được truy cập qua ranh giới mô-đun; Java access modifier quyết định kiểu và thành viên nào được truy cập bên trong package đó.

## 4. Access modifier của Java vẫn được áp dụng

| Modifier | Phạm vi chính |
|---|---|
| public | Mã gọi có readability, package được xuất và thỏa các quy tắc Java khác |
| protected | Cùng package hoặc theo quy tắc truy cập từ subclass |
| Không ghi modifier (package-private) | Chỉ trong cùng package |
| private | Trong lớp khai báo và các trường hợp nestmate được Java cho phép |

Các tình huống thường gặp:

- Lớp public trong package không được xuất: mô-đun khác không thể dùng lớp đó qua JPMS.
- Lớp public trong package đã xuất nhưng constructor package-private: consumer nhìn thấy kiểu nhưng không thể gọi constructor.
- Thành viên private không thể được gọi trực tiếp từ mã Java bên ngoài lớp theo access control thông thường.
- Thành viên protected vẫn chịu quy tắc subclass; exports không bỏ qua quy tắc này.

Với named module, một package không được chia tùy tiện giữa nhiều mô-đun. Tránh split package vì nó có thể làm việc biên dịch hoặc phân giải mô-đun thất bại.

## 5. exports khác opens

exports phục vụ truy cập API thông thường qua ranh giới mô-đun. opens phục vụ truy cập phản chiếu sâu (deep reflection) ở runtime.

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.orm;
}
~~~

Package com.acme.domain.api được công khai để mô-đun đọc domain sử dụng các kiểu public. Package com.acme.domain.model được mở cho com.acme.orm để framework có thể dùng reflection truy cập thành viên không công khai khi cần ánh xạ object.

opens không thay thế exports cho việc import và gọi API thông thường trong mã nguồn. Ngược lại, exports không cấp quyền deep reflection vào field hoặc method private.

Nếu cần mở mọi package cho reflection, có thể khai báo open module. Đây là phạm vi rộng hơn; với framework, nên mở đúng package và đúng mô-đun đích.

## 6. Khi thiếu một điều kiện

| Tình huống | Nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy mô-đun dependency khi chạy | Mô-đun không có trên module path hoặc không được phân giải | Kiểm tra --module-path và tên mô-đun |
| Package không nhìn thấy trong mô-đun gọi | Thiếu requires hoặc mô-đun chưa đọc được | Kiểm tra module-info.java của mô-đun gọi |
| Mô-đun đọc được dependency nhưng không truy cập được package | Package chưa được exports cho consumer | Kiểm tra exports hoặc qualified exports |
| Kiểu public dùng được nhưng method không gọi được | Modifier của thành viên không cho phép truy cập | Kiểm tra access modifier |
| Framework không truy cập được field private | Package chưa được mở cho deep reflection | Kiểm tra opens có phạm vi phù hợp |
| Consumer không đọc được kiểu dependency trong chữ ký API | Readability chưa được truyền qua hợp đồng API | Xem xét requires transitive |

Thông báo lỗi chính xác có thể khác theo phiên bản JDK và cách biên dịch. Nguyên nhân thường thuộc một trong ba nhóm: mô-đun không đọc được, package không được xuất hoặc access modifier của Java không cho phép.

## 7. Ví dụ chạy được với hai mô-đun

Ví dụ này minh họa readability, exports và Java access modifier. Mô-đun geometry xuất package API và giữ package internal ở bên trong; app đọc geometry và sử dụng Point.

Cấu trúc thư mục:

~~~text
src/
├── com.acme.geometry/
│   ├── module-info.java
│   ├── com/acme/geometry/api/Point.java
│   └── com/acme/geometry/internal/DebugInfo.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

**Mô-đun geometry — src/com.acme.geometry/module-info.java:**

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

**Kiểu public trong package API — src/com.acme.geometry/com/acme/geometry/api/Point.java:**

~~~java
package com.acme.geometry.api;

public final class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() {
        return x;
    }

    public int y() {
        return y;
    }

    String internalCode() {
        return x + ":" + y;
    }
}
~~~

**Kiểu public trong package nội bộ — src/com.acme.geometry/com/acme/geometry/internal/DebugInfo.java:**

~~~java
package com.acme.geometry.internal;

public final class DebugInfo {
    public static String describe() {
        return "internal";
    }
}
~~~

DebugInfo là public nhưng package của nó không được xuất.

**Mô-đun ứng dụng — src/com.acme.app/module-info.java:**

~~~java
module com.acme.app {
    requires com.acme.geometry;
}
~~~

**Lớp chạy — src/com.acme.app/com/acme/app/Main.java:**

~~~java
package com.acme.app;

import com.acme.geometry.api.Point;

public class Main {
    public static void main(String[] args) {
        Point point = new Point(3, 4);
        System.out.println("x=" + point.x() + ", y=" + point.y());
    }
}
~~~

Mở terminal tại thư mục chứa src/, dùng JDK 17 trở lên và chạy:

~~~bash
javac --release 17 -d out --module-source-path src -m com.acme.geometry,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Stdout chính xác:

~~~text
x=3, y=4
~~~

Ứng dụng chạy được vì app khai báo requires geometry, geometry xuất package api, và Point cùng các thành viên được gọi đều có quyền truy cập public.

### Thử bỏ từng điều kiện

Các thay đổi sau dùng để chẩn đoán:

- Bỏ requires com.acme.geometry khỏi module descriptor của app: app không đọc được geometry nên không thể tham chiếu Point.
- Bỏ exports com.acme.geometry.api khỏi geometry: app có readability nhưng package API không được xuất.
- Import com.acme.geometry.internal.DebugInfo: dù DebugInfo là public, package internal không được xuất nên app không thể sử dụng.
- Gọi point.internalCode(): package API đã được xuất và Point public, nhưng method package-private không cho phép mã ở package app gọi.

Các phép thử đã được biên dịch bằng JDK 24. Trường hợp hợp lệ chạy với stdout x=3, y=4; các trường hợp thiếu readability, truy cập package chưa export và gọi method package-private đều bị trình biên dịch từ chối như mong đợi.

## 8. Readability trong classpath và module path

JPMS vẫn hỗ trợ mã Java chạy từ classpath để duy trì khả năng tương thích:

- Mã trên classpath thuộc unnamed module của class loader tương ứng.
- Unnamed module có thể đọc các named module đã được phân giải.
- Named module không tự động đọc unnamed module.
- JAR có module descriptor khi đặt trên module path có thể được phân giải như explicit module; JAR không có descriptor có thể được xử lý như automatic module trên module path.

Với ứng dụng modular, nên khai báo dependency rõ ràng trong module descriptor. Khi một phần hệ thống vẫn chạy trên classpath, cần hiểu ranh giới unnamed module để không giả định rằng quan hệ phụ thuộc của classpath và named module giống hệt nhau.

Không nên xuất package nội bộ chỉ để làm cho mã bên ngoài biên dịch được. Hãy xác định package đó có thực sự là hợp đồng được hỗ trợ hay không, rồi quyết định exports, qualified exports hoặc giữ package ở phạm vi nội bộ.

## 9. Quy trình chẩn đoán

Khi compiler báo một kiểu hoặc package không thể truy cập, kiểm tra theo thứ tự:

1. **Xác định mô-đun sở hữu kiểu:** xem package và module descriptor của thư viện.
2. **Kiểm tra readability:** mô-đun gọi đã khai báo requires chưa? Dependency có trên module path không?
3. **Kiểm tra exports:** package có được xuất không? Nếu là qualified exports, mô-đun gọi có nằm trong danh sách được phép không?
4. **Kiểm tra kiểu:** class, interface hoặc record có phải public không?
5. **Kiểm tra thành viên:** constructor, method hoặc field có modifier cho phép truy cập không?
6. **Kiểm tra reflection:** nếu framework truy cập private member, package có được opens cho mô-đun framework không?
7. **Kiểm tra runtime:** module path lúc chạy có khớp cấu hình biên dịch và dependency cần thiết không?

Có thể dùng công cụ JDK để quan sát mô-đun và dependency:

~~~bash
java --show-module-resolution --module-path out -m com.acme.app/com.acme.app.Main
jar --describe-module --file geometry.jar
jdeps --module-path libs --check com.acme.app
~~~

Các lệnh này giúp xem quá trình phân giải mô-đun, descriptor của JAR và tính nhất quán dependency. Hãy điều chỉnh module descriptor trước khi cân nhắc tùy chọn mở quyền ở dòng lệnh. --add-exports và --add-opens có thể hữu ích trong quá trình chuyển đổi hoặc tích hợp framework, nhưng không nên thay thế lâu dài cho hợp đồng mô-đun được thiết kế rõ ràng.

## 10. Nguyên tắc thiết kế API modular

- Xuất package chứa API ổn định mà consumer cần dùng.
- Giữ package implementation không xuất nếu không có nhu cầu công khai.
- Chỉ dùng qualified exports khi cần giới hạn consumer cụ thể.
- Dùng requires transitive khi dependency là một phần của chữ ký API mà consumer cần đọc.
- Dùng requires static cho dependency chỉ cần ở compile-time và thực sự tùy chọn khi chạy.
- Dùng opens có phạm vi hẹp cho framework cần deep reflection.
- Tiếp tục dùng access modifier của Java để kiểm soát kiểu và thành viên bên trong package đã xuất.

Một API modular dễ bảo trì khi người tiêu thụ chỉ nhìn thấy những package và kiểu được chủ ý công khai. Readability, exports và access modifier là các lớp kiểm soát bổ sung; mỗi lớp cần được khai báo đúng với vai trò của nó.

## Kết luận

Readability trả lời mô-đun gọi có được phép đọc mô-đun cung cấp hay không. exports quyết định package nào được công khai qua ranh giới mô-đun. Access modifier của Java quyết định kiểu và thành viên nào có thể được gọi. Với reflection, opens cung cấp quyền truy cập sâu ở runtime theo phạm vi được khai báo.

Khi một kiểu không truy cập được, hãy kiểm tra lần lượt requires, exports và modifier của kiểu/thành viên. Cách phân tách này giúp chẩn đoán lỗi nhanh, thiết kế API JPMS rõ ràng và giữ phần triển khai nội bộ được đóng gói trong Java hiện đại.
