# Module descriptor được biên dịch thành Module attribute

Trong Java Platform Module System (JPMS), file `module-info.java` là nơi khai báo tên module, dependency và các ranh giới truy cập. Khi biên dịch, `javac` chuyển khai báo này thành một file class đặc biệt có tên **`module-info.class`**. Thông tin mô tả module được lưu trong class-file attribute có tên **`Module`**.

Điều này giúp module system đọc được cấu trúc module từ bytecode hoặc từ một modular JAR mà không cần mã nguồn `module-info.java`. Cần phân biệt ba thứ: file nguồn `module-info.java`, file nhị phân `module-info.class`, và đối tượng `java.lang.Module` mà JVM/module system biểu diễn khi ứng dụng chạy.

## 1. Từ module-info.java đến module-info.class

Một module được khai báo bằng file có tên cố định `module-info.java`, đặt ở thư mục gốc của source set module:

~~~text
src/
└── com.acme.greeter/
    ├── module-info.java
    └── com/
        └── acme/
            └── greeter/
                └── api/
                    └── Greeter.java
~~~

Ví dụ nội dung `module-info.java`:

~~~java
module com.acme.greeter {
    requires java.logging;
    exports com.acme.greeter.api;
}
~~~

Khai báo trên nói rằng:

- Tên module là `com.acme.greeter`.
- Module phụ thuộc vào `java.logging`.
- Package `com.acme.greeter.api` được export để module khác có thể sử dụng các kiểu public trong package đó.

Biên dịch module:

~~~bash
javac --module-source-path src -d out -m com.acme.greeter
~~~

Sau khi biên dịch, cấu trúc đầu ra có dạng:

~~~text
out/
└── com.acme.greeter/
    ├── module-info.class
    └── com/
        └── acme/
            └── greeter/
                └── api/
                    └── Greeter.class
~~~

`module-info.java` không trở thành một lớp Java thông thường tên `ModuleInfo`. Compiler tạo file đặc biệt `module-info.class`. File này không chứa các method nghiệp vụ; nó mang metadata mô tả module để công cụ và module system sử dụng.

Khi đóng gói thành modular JAR, `module-info.class` nằm ở thư mục gốc của JAR, bên cạnh các package đã biên dịch. Vì vậy, công cụ có thể tìm descriptor mà không cần biết source tree ban đầu.

## 2. Module attribute trong class file

Theo định dạng class file của JVM, `module-info.class` là một loại class file đặc biệt. Một số đặc điểm quan trọng:

- Cờ truy cập của class file có bit `ACC_MODULE` với giá trị `0x8000`.
- `this_class` tham chiếu đến tên đặc biệt `module-info`.
- `super_class`, danh sách interface, field và method đều rỗng theo cấu trúc dành cho module descriptor.
- Class file phải có attribute `Module`, nơi lưu thông tin khai báo module.

Một class file Java thông thường mô tả một lớp với field, method và các attribute liên quan. `module-info.class` dùng cùng định dạng bao ngoài của class file nhưng tuân theo các ràng buộc riêng của module descriptor.

### Các phần dữ liệu trong Module attribute

Attribute `Module` lưu các nhóm thông tin sau:

| Thành phần | Dữ liệu được lưu | Nguồn khai báo tương ứng |
| --- | --- | --- |
| Module header | Tên module, cờ module, phiên bản module nếu có | `module name [version]` |
| Requires | Các module được yêu cầu, cờ của từng dependency và phiên bản yêu cầu nếu có | `requires` |
| Exports | Các package được export, cờ và danh sách module đích nếu export có giới hạn | `exports` |
| Opens | Các package được mở cho reflection, cờ và danh sách module đích nếu opens có giới hạn | `opens` |
| Uses | Các service interface mà module tiêu thụ | `uses` |
| Provides | Service interface và các implementation mà module cung cấp | `provides ... with ...` |

Các tên trong attribute không nhất thiết được lưu lặp lại dưới dạng chuỗi văn bản ở từng vị trí. Những trường trong `Module` trỏ đến các entry trong **constant pool** của class file. Module name sử dụng hằng `CONSTANT_Module`, package name sử dụng `CONSTANT_Package`, còn tên class được tham chiếu bằng `CONSTANT_Class`.

Nhờ cách biểu diễn này, JVM và các công cụ có thể phân tích descriptor theo cấu trúc nhị phân chuẩn.

### Requires và các cờ dependency

Mỗi entry trong bảng `requires` chứa module được yêu cầu cùng các cờ mô tả quan hệ:

| Khai báo Java | Cờ trong class file | Ý nghĩa |
| --- | --- | --- |
| `requires X;` | Không có cờ đặc biệt bắt buộc | Dependency thông thường |
| `requires transitive X;` | `ACC_TRANSITIVE` (`0x0020`) | Module đọc module hiện tại cũng được đọc X |
| `requires static X;` | `ACC_STATIC_PHASE` (`0x0040`) | Dependency cần ở compile-time, có thể vắng mặt ở run-time |

Một số cờ khác có thể xuất hiện trong descriptor, ví dụ `ACC_SYNTHETIC` hoặc `ACC_MANDATED`, để biểu thị dependency được compiler hoặc môi trường tạo ra theo quy tắc của nền tảng. Các cờ này là metadata, không phải từ khóa mà lập trình viên thường tự viết trong `module-info.java`.

### Exports và opens

Mỗi entry trong `exports` tham chiếu tới một package. Nếu package được export có giới hạn, entry còn chứa danh sách module được phép đọc package đó.

Ví dụ:

~~~java
module com.acme.greeter {
    exports com.acme.greeter.api;
    exports com.acme.greeter.spi to com.acme.plugin;
}
~~~

Trong `Module` attribute, hai package được ghi trong nhóm `exports`; package `com.acme.greeter.spi` có thêm danh sách module đích `com.acme.plugin`.

Nhóm `opens` có cấu trúc tương tự nhưng mô tả quyền truy cập reflection sâu khi chạy:

~~~java
module com.acme.greeter {
    opens com.acme.greeter.model to com.acme.json;
}
~~~

`exports` và `opens` không thể thay thế nhau. Export phục vụ truy cập API theo quy tắc Java thông thường; opens phục vụ reflection, chẳng hạn framework cần truy cập member không public.

### Uses và provides

Descriptor còn ghi lại khai báo Service Provider Interface:

~~~java
module com.acme.greeter {
    uses com.acme.greeter.spi.GreetingProvider;
    provides com.acme.greeter.spi.GreetingProvider
        with com.acme.greeter.internal.DefaultGreetingProvider;
}
~~~

- `uses` lưu service type mà module cần tìm implementation.
- `provides` lưu service type và danh sách provider class do module cung cấp.

Các thông tin này được lưu trong hai nhóm riêng của `Module` attribute. Nhờ vậy, cơ chế `ServiceLoader` có thể phát hiện provider từ metadata module mà không cần dựa vào file cấu hình classpath kiểu cũ.

## 3. Các attribute khác liên quan đến module

Ngoài `Module`, `module-info.class` có thể chứa các attribute bổ sung:

| Attribute | Vai trò |
| --- | --- |
| `ModulePackages` | Liệt kê các package thuộc module. |
| `ModuleMainClass` | Ghi nhận lớp main của module nếu có. |
| `ModuleTarget` | Có thể ghi nhận nền tảng hoặc target mà module hướng tới. |
| `ModuleResolution` | Lưu các cờ liên quan đến cách phân giải module. |
| `ModuleHashes` | Lưu hash của các module khác trong một số quy trình đóng gói hoặc kiểm soát tính toàn vẹn. |

Không phải module nào cũng có tất cả các attribute tùy chọn trên. Attribute cốt lõi để mô tả khai báo module là `Module`; các attribute khác bổ sung thông tin phục vụ đóng gói, khởi chạy hoặc công cụ.

Đặc biệt, `ModulePackages` không thay thế `exports`. Một package có thể thuộc module nhưng không được export. `ModulePackages` nói package nào tồn tại trong module; `exports` nói package nào được công khai cho module khác.

## 4. Quan sát Module attribute bằng javap

Có thể xem metadata nhị phân mà compiler tạo ra bằng `javap -v`:

~~~bash
javap -v out/com.acme.greeter/module-info.class
~~~

Trong kết quả, tìm phần `Module:`. Với ví dụ ở trên, nội dung sẽ thể hiện các thông tin tương đương:

~~~text
Module:
  #... com.acme.greeter
  requires
    #... java.base
    #... java.logging
  exports
    #... com/acme/greeter/api
~~~

Các số `#...` là chỉ số constant-pool trong output thực tế. Chỉ số và thứ tự entry phụ thuộc vào nội dung class file, nên không nên xem chúng là giá trị cố định.

Có thể dùng lệnh sau để xem descriptor mà JAR công bố:

~~~bash
jar --describe-module --file build/libs/greeter.jar
~~~

Lệnh `jar --describe-module` trình bày descriptor ở dạng dễ đọc. `javap -v` hữu ích hơn khi muốn quan sát cấu trúc class file và constant pool. Cả hai lệnh đều giúp kiểm tra kết quả biên dịch/đóng gói mà không cần đọc lại source.

## 5. Module system sử dụng descriptor như thế nào?

Khi compiler biên dịch một module phụ thuộc vào module khác, nó có thể đọc `module-info.class` của dependency trên module path để biết tên module, các dependency và package được export.

Khi Java launcher khởi động ứng dụng modular, module system cũng đọc descriptor trong các module tìm được trên module path. Từ root module và các quan hệ `requires`, nó phân giải module graph, kiểm tra dependency bắt buộc và thiết lập khả năng đọc module.

Có thể hình dung luồng dữ liệu:

~~~text
module-info.java
      │
      │ javac
      ▼
module-info.class
      │
      ├── Module attribute
      ├── ModulePackages (nếu có)
      └── các module attribute bổ sung (nếu có)
                │
                ├── javac đọc descriptor dependency khi compile
                │
                └── module system đọc descriptor khi resolve/run
~~~

Điểm quan trọng: `Module` attribute là **dữ liệu nhị phân trong class file**. Nó không phải đối tượng `java.lang.Module`. Khi ứng dụng chạy, module system sử dụng metadata này để xây dựng biểu diễn module trong runtime.

### Automatic module là trường hợp khác

Một JAR cũ không có `module-info.class` vẫn có thể được đưa lên module path và được xem như automatic module. Khi đó, module system suy ra descriptor tự động, có thể dựa trên thuộc tính `Automatic-Module-Name` trong manifest hoặc tên JAR.

Vì vậy, không phải mọi module trên module path đều có file `module-info.class` do compiler tạo. Với **explicit named module**, descriptor được khai báo rõ bằng `module-info.java` và biên dịch thành `module-info.class`; với **automatic module**, descriptor được suy ra từ JAR.

## 6. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `module-info.java` được biên dịch thành một class Java thông thường | Nó tạo `module-info.class`, một class file đặc biệt có `ACC_MODULE` và `Module` attribute. |
| Tên file `module-info.class` là tên module | Tên module thực tế được lưu trong `Module` attribute; tên file là quy ước cố định. |
| Tất cả package trong module đều được public | Package có thể tồn tại trong module nhưng không được export. |
| `ModulePackages` và `exports` giống nhau | Một bên liệt kê package của module; bên kia công bố package cho module khác. |
| `Module` attribute chính là đối tượng `java.lang.Module` | Attribute là metadata nhị phân; runtime dùng metadata đó để tạo biểu diễn module. |
| Mọi JAR trên module path đều có `module-info.class` | Automatic module có thể không chứa descriptor class file. |
| Có thể sửa nội dung `Module` attribute bằng cách sửa source mà không biên dịch lại | Thay đổi `module-info.java` cần được biên dịch lại để cập nhật `module-info.class` trong output/JAR. |

## 7. Quy trình kiểm tra khi descriptor không đúng như mong đợi

Khi một dependency không được nhận diện hoặc package không được export như dự kiến, hãy kiểm tra theo thứ tự:

1. **Kiểm tra source:** mở đúng `module-info.java` và xác nhận `requires`, `exports`, `opens`, `uses`, `provides`.
2. **Biên dịch lại module:** bảo đảm file `module-info.class` được tạo từ source mới nhất.
3. **Kiểm tra output:** dùng `javap -v path/to/module-info.class` và đọc phần `Module:`.
4. **Kiểm tra JAR:** dùng `jar --describe-module --file path/to/module.jar` để xác nhận descriptor trong artifact được phát hành.
5. **Kiểm tra module path thực tế:** bảo đảm compiler và launcher đang đọc đúng thư mục/JAR vừa kiểm tra, tránh dùng nhầm bản cũ trong cache hoặc thư mục build khác.

Nếu source đúng nhưng output sai, vấn đề thường nằm ở bước biên dịch hoặc artifact cũ. Nếu output đúng nhưng runtime vẫn phân giải sai, hãy kiểm tra module path và root module mà launcher thực sự sử dụng.

## Kết luận

`module-info.java` là mô tả module ở cấp source. Compiler chuyển mô tả đó thành `module-info.class`, trong đó attribute `Module` lưu tên module, flags, dependency, package export/open, service usage và service provider. Các công cụ như `javap -v` và `jar --describe-module` cho phép quan sát metadata này sau biên dịch hoặc đóng gói.

Hiểu mối liên hệ giữa source descriptor, `Module` attribute và runtime module giúp xác định chính xác lỗi nằm ở khai báo, kết quả biên dịch hay artifact mà ứng dụng đang sử dụng.