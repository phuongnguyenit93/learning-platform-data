# Split package khi có nhiều ModuleLayer trong Java

## 1. Mục tiêu

Khi một ứng dụng Java dùng JPMS (Java Platform Module System) để nạp nhiều plugin, phiên bản thư viện hoặc tập module theo từng `ModuleLayer`, hai module có thể chứa các lớp thuộc cùng một package, ví dụ `com.example.plugin.internal`. Hiện tượng này gọi là **split package**.

Sau bài này, bạn có thể:

- Phân biệt tên package, module, class loader và layer khi phân tích xung đột.
- Biết trường hợp split package gây lỗi lúc resolve module hoặc lúc tạo layer.
- Tạo hai layer độc lập có cùng tên package mà các lớp vẫn được cô lập.
- Chọn cách sửa phù hợp cho ứng dụng modular hoặc hệ thống plugin.

**Ý chính:** package không nhất thiết phải có tên duy nhất trong toàn bộ JVM. Điều quan trọng là các module nào cùng được đọc, và mỗi module được ánh xạ vào class loader nào. `ModuleLayer` tạo phạm vi cấu hình module; `ClassLoader` thực sự định nghĩa lớp.

## 2. Các khái niệm cần nắm

| Khái niệm | Vai trò |
| --- | --- |
| Package | Nhóm lớp có tên chung, như `com.example.shared`. |
| Named module | Đơn vị JPMS khai báo bởi `module-info.java`; chứa tập package, quan hệ `requires`, `exports`, `opens` và dịch vụ. |
| `Configuration` | Đồ thị module sau khi giải quyết phụ thuộc và quan hệ đọc. |
| `ModuleLayer` | Tập module đã được định nghĩa từ một `Configuration`, có thể liên kết với các layer cha. |
| Class loader | Định nghĩa lớp từ bytecode. Hai lớp cùng tên đầy đủ nhưng do hai loader khác nhau định nghĩa là hai kiểu khác nhau. |
| Split package | Cùng một tên package xuất hiện ở hai hay nhiều module hoặc nguồn lớp khác nhau. |

Hai câu hỏi phải được tách riêng:

1. **Phần giải quyết module:** Một module có thể đọc hai module cùng xuất một package hay không? Nếu có xung đột khả năng đọc, quá trình resolution có thể thất bại.
2. **Phần ánh xạ class loader:** Nhiều named module chứa cùng package có bị gán vào một class loader hay không? Nếu có, Java không thể định nghĩa chúng như các module riêng biệt trong cùng loader.

Không nên suy luận “hai layer có package trùng tên thì luôn lỗi”. Cũng không nên suy luận “dùng layer khác nhau thì chắc chắn không lỗi”: cấu hình phụ thuộc, quan hệ đọc và cách chọn loader vẫn quan trọng.

## 3. Split package xuất hiện ở đâu?

Xét hai module có cấu trúc:

```text
module demo.plugin.alpha
  └── demo.plugin.impl.Greeter

module demo.plugin.beta
  └── demo.plugin.impl.Greeter
```

Cả hai chứa package `demo.plugin.impl`. Kết quả tùy cấu hình:

| Tình huống | Kết quả cần chú ý |
| --- | --- |
| Hai module cùng được gán **một class loader** | Không thể cùng sở hữu package đó trong loader; tạo layer có thể ném `LayerInstantiationException`. |
| Hai module ở cùng layer nhưng được gán **hai loader riêng** | Có thể định nghĩa nếu cấu hình module hợp lệ và không phát sinh xung đột readability/export. |
| Mỗi module ở **một layer anh em**, mỗi layer tạo loader riêng | Có thể cùng chứa tên package, thậm chí cùng tên lớp, nhưng hai lớp có định danh kiểu khác nhau. |
| Một module đọc hai module đều `exports` cùng package cho nó | Resolver có thể ném `ResolutionException`, dù dự định dùng nhiều loader. |
| Hai lớp có cùng tên nhưng được nạp từ loader khác nhau | `Class<?>` khác nhau; không thể cast qua lại chỉ vì cùng tên lớp. |

Đặc biệt, `defineModulesWithOneLoader(...)` **tạo một class loader mới** để định nghĩa các module trong cấu hình layer đó. Tham số `parentLoader` chỉ là loader cha cho việc ủy quyền. Hai lần gọi độc lập thường tạo hai loader định nghĩa khác nhau, ngay cả khi truyền cùng một `parentLoader`.

## 4. Ví dụ chạy được: hai layer anh em có cùng package

Ta tạo hai named module khác tên, cùng package và cùng tên lớp. Chúng được nạp vào hai `ModuleLayer` độc lập, có cùng layer cha là boot layer.

### 4.1. Cấu trúc thư mục

```text
project/
├── src/
│   ├── alpha/
│   │   ├── module-info.java
│   │   └── demo/plugin/impl/Greeter.java
│   ├── beta/
│   │   ├── module-info.java
│   │   └── demo/plugin/impl/Greeter.java
│   └── host/
│       └── LayerDemo.java
└── mods/                         # sản phẩm biên dịch
```

File `src/alpha/module-info.java`:

```java
module demo.plugin.alpha {
    exports demo.plugin.impl;
}
```

File `src/alpha/demo/plugin/impl/Greeter.java`:

```java
package demo.plugin.impl;

public final class Greeter {
    public String message() {
        return "Xin chào từ alpha";
    }
}
```

File `src/beta/module-info.java`:

```java
module demo.plugin.beta {
    exports demo.plugin.impl;
}
```

File `src/beta/demo/plugin/impl/Greeter.java`:

```java
package demo.plugin.impl;

public final class Greeter {
    public String message() {
        return "Xin chào từ beta";
    }
}
```

Ở đây việc hai module khai báo cùng `exports demo.plugin.impl` là có chủ đích: ta muốn quan sát cùng tên package trong hai phạm vi layer tách biệt. Trong thiết kế thực tế, nên giữ package triển khai ở trạng thái không export nếu host không cần truy cập trực tiếp.

### 4.2. Host nạp từng module vào một layer

File `src/host/LayerDemo.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class LayerDemo {
    private static ModuleLayer loadLayer(String moduleName, Path modulePath) {
        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(modulePath);

        Configuration config = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of(moduleName)
        );

        // Mỗi lần gọi tạo loader mới cho layer vừa định nghĩa.
        return parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader()
        );
    }

    public static void main(String[] args) throws Exception {
        ModuleLayer alphaLayer = loadLayer(
                "demo.plugin.alpha", Path.of("mods", "demo.plugin.alpha")
        );
        ModuleLayer betaLayer = loadLayer(
                "demo.plugin.beta", Path.of("mods", "demo.plugin.beta")
        );

        Class<?> alphaClass = alphaLayer
                .findLoader("demo.plugin.alpha")
                .loadClass("demo.plugin.impl.Greeter");
        Class<?> betaClass = betaLayer
                .findLoader("demo.plugin.beta")
                .loadClass("demo.plugin.impl.Greeter");

        System.out.println(alphaClass.getName().equals(betaClass.getName()));
        System.out.println(alphaClass == betaClass);
        System.out.println(alphaClass.getClassLoader()
                == betaClass.getClassLoader());
        System.out.println(alphaClass.getModule().getName());
        System.out.println(betaClass.getModule().getName());
    }
}
```

`ModuleFinder.of(modulePath)` trỏ tới thư mục module đã biên dịch, gồm `module-info.class`. Mỗi `resolve(...)` chỉ chọn một plugin làm root; `defineModulesWithOneLoader(...)` của mỗi lần nạp tạo loader cho layer tương ứng.

### 4.3. Biên dịch và chạy

Ví dụ lệnh cho Bash (Java 11 trở lên; Java 17 hoặc 21 LTS đều phù hợp):

```bash
mkdir -p mods/demo.plugin.alpha mods/demo.plugin.beta out/host

javac -d mods/demo.plugin.alpha \
  src/alpha/module-info.java src/alpha/demo/plugin/impl/Greeter.java

javac -d mods/demo.plugin.beta \
  src/beta/module-info.java src/beta/demo/plugin/impl/Greeter.java

javac -d out/host src/host/LayerDemo.java
java -cp out/host LayerDemo
```

Đầu ra kỳ vọng:

```text
true
false
false
demo.plugin.alpha
demo.plugin.beta
```

Giải thích:

- `true`: hai lớp có cùng tên nhị phân `demo.plugin.impl.Greeter`.
- `false` thứ nhất: chúng là hai đối tượng `Class` khác nhau.
- `false` thứ hai: chúng do hai loader khác nhau định nghĩa.
- Tên module cho thấy chúng thực sự thuộc hai named module khác nhau.

Đây là cách cô lập hai triển khai có tên package trùng nhau mà không phải đổi package trong ví dụ. Tuy vậy, một đối tượng `Greeter` do layer alpha tạo ra không thể được ép kiểu sang `Greeter` của layer beta.

## 5. Khi gộp hai module vào cùng layer sẽ ra sao?

Nếu đặt cả hai module vào cùng một `Configuration` rồi cố gán **một** loader:

```java
ModuleLayer parent = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(
        Path.of("mods", "demo.plugin.alpha"),
        Path.of("mods", "demo.plugin.beta")
);
Configuration config = parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("demo.plugin.alpha", "demo.plugin.beta")
);

// Hai module đều chứa demo.plugin.impl:
ModuleLayer layer = parent.defineModulesWithOneLoader(
        config, ClassLoader.getSystemClassLoader()
);
```

Với cấu hình không bị từ chối trước đó ở bước resolution, thao tác định nghĩa một loader cho cả hai module sẽ thất bại với `LayerInstantiationException` do package trùng. Chuỗi thông báo chính xác tùy phiên bản JDK.

Có thể đổi thành:

```java
ModuleLayer layer = parent.defineModulesWithManyLoaders(
        config, ClassLoader.getSystemClassLoader()
);
```

Phương thức này tạo loader riêng cho từng module trong cấu hình, vì vậy giải quyết ràng buộc **cùng package trong cùng loader**. Nhưng nó **không** loại bỏ xung đột đồ thị module: nếu một module đọc hai module cùng export một package cho nó, `Configuration.resolve(...)` vẫn có thể thất bại trước khi tạo layer.

Lựa chọn nhiều loader cũng có chi phí: nhiều class loader, phiên bản lớp tách biệt, khó chia sẻ kiểu triển khai hoặc trạng thái tĩnh. Đừng dùng nó chỉ để che một thiết kế package trùng không cần thiết.

## 6. Vì sao resolution có thể lỗi dù loader khác nhau?

Giả sử `demo.consumer` có:

```java
module demo.consumer {
    requires demo.plugin.alpha;
    requires demo.plugin.beta;
}
```

Nếu cả hai plugin đều `exports demo.plugin.impl` cho `demo.consumer`, consumer nhìn thấy hai module cung cấp cùng package. JPMS không cho phép đồ thị đọc dẫn tới việc một module thấy hai package được export có cùng tên. Resolver có thể báo `java.lang.module.ResolutionException` với thông tin về các module và package xung đột.

Như vậy cần phân biệt:

- **Xung đột ở resolution**: sai quan hệ `requires`/`exports`, không tạo được `Configuration` hợp lệ.
- **Xung đột ở layer instantiation**: cấu hình có thể hợp lệ, nhưng ánh xạ các module có package trùng vào chung loader không hợp lệ.
- **Xung đột lúc sử dụng lớp**: dù hai layer nạp thành công, lớp từ hai loader không cùng một kiểu; thao tác cast, reflection hoặc truyền đối tượng sai kiểu có thể thất bại.

Tách layer phù hợp khi mỗi plugin được giải quyết và nạp riêng; host chỉ tương tác với một API chung ổn định, không trực tiếp `requires` toàn bộ các module plugin chứa package trùng nhau.

## 7. Thiết kế plugin đúng hướng

Một kiến trúc thường dễ bảo trì hơn:

```text
Boot/parent layer
  └── demo.plugin.api
       └── demo.plugin.api.Plugin  (giao diện chung)
          ↑                    ↑
          │                    │
Child layer A             Child layer B
  demo.plugin.alpha         demo.plugin.beta
  loader A                  loader B
  demo.plugin.impl          demo.plugin.impl
```

Đặt interface `Plugin` trong module API do layer cha cung cấp; mỗi plugin có thể dùng package triển khai riêng, hoặc trong trường hợp cô lập thực sự cần thiết mới giữ tên package trùng nhau. Mỗi plugin khai báo phụ thuộc API và cung cấp triển khai:

```java
module demo.plugin.alpha {
    requires demo.plugin.api;
    provides demo.plugin.api.Plugin
        with demo.plugin.impl.AlphaPlugin;
}
```

Ở plugin còn lại có thể dùng:

```java
module demo.plugin.beta {
    requires demo.plugin.api;
    provides demo.plugin.api.Plugin
        with demo.plugin.impl.BetaPlugin;
}
```

Host có thể tìm provider ở từng layer thông qua `ServiceLoader.load(layer, Plugin.class)`, với `Plugin.class` được nạp từ module API chung. Vì interface thuộc cùng module API/loader cha, host trao đổi qua kiểu `Plugin` ổn định mà không cần cast giữa các lớp triển khai trùng tên.

Một số nguyên tắc:

1. Đặt API, DTO và hợp đồng dịch vụ dùng chung ở module/layer cha. Những kiểu truyền qua ranh giới layer phải có định danh lớp thống nhất.
2. Chỉ giữ các package trùng tên ở vùng triển khai thực sự được cô lập. Nếu có quyền sửa mã nguồn, đặt tên package duy nhất cho từng module thường đơn giản hơn.
3. Dùng `ModuleLayer.findLoader(moduleName)` để nạp lớp của đúng module; tránh mặc định rằng `ClassLoader.getSystemClassLoader()` tìm được mọi plugin.
4. Giải phóng các tham chiếu đến `Class`, instance, thread, cache, `ServiceLoader` và loader khi muốn dỡ plugin. Layer không có lệnh `unload()`; việc thu hồi phụ thuộc garbage collector và các tham chiếu còn sống.
5. Không coi `--add-reads`, `--add-exports` hoặc `--add-opens` là biện pháp sửa split package. Chúng điều chỉnh truy cập, không biến hai module có package trùng thành một package hợp lệ trong một loader.

## 8. Chẩn đoán lỗi theo từng giai đoạn

| Dấu hiệu | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| `ResolutionException` khi `resolve` | Module nào `requires` hoặc đọc đồng thời hai nguồn export cùng package? | Sửa đồ thị module, tách các plugin theo layer, hoặc di chuyển package về một module chung. |
| `LayerInstantiationException` khi `defineModulesWithOneLoader` | Hai module trong cấu hình có cùng package không? | Dùng loader riêng nếu kiến trúc cho phép, hoặc loại bỏ split package. |
| `ClassNotFoundException` khi tìm plugin | Có đang gọi loader của đúng module/layer và đường dẫn module có đúng không? | Lấy loader qua `layer.findLoader(moduleName)`, kiểm tra tên module và artefact biên dịch. |
| `ClassCastException` dù tên lớp giống nhau | Hai kiểu có cùng defining class loader không? | Chia sẻ interface/DTO từ layer cha; không ép kiểu qua hai bản sao lớp triển khai. |
| `IllegalAccessException` hoặc `InaccessibleObjectException` | Package có `exports`/`opens` phù hợp không? | Điều chỉnh quyền truy cập theo đúng nhu cầu; không nhầm với xung đột split package. |

Để quan sát nhanh nguồn gốc lớp ở runtime:

```java
System.out.println(type.getName());
System.out.println(type.getModule());
System.out.println(type.getClassLoader());
System.out.println(type.getModule().getLayer());
```

Khi debug, đối chiếu cả **tên lớp + module + loader + layer**. Chỉ nhìn tên package hoặc tên lớp thường không đủ để giải thích tại sao hai đối tượng không tương thích.

## 9. Khi nào nên dùng giải pháp nào?

- **Thư viện và ứng dụng modular thông thường:** tránh split package; gom package vào một named module, hoặc đổi tên package theo module. Đây là phương án dễ bảo trì nhất.
- **Nhiều plugin hoặc nhiều phiên bản phụ thuộc cần tồn tại song song:** cân nhắc các layer anh em với loader riêng, giữ API chung trong layer cha và giao tiếp qua service/interface.
- **Nhiều module ở một layer nhưng package bị trùng:** `defineModulesWithManyLoaders` có thể hỗ trợ ở bước định nghĩa lớp, với điều kiện cấu hình resolution không có xung đột readability; đánh giá rõ chi phí cách ly kiểu.
- **Có package trên classpath và module path:** kiểm tra thêm hành vi của unnamed module và cơ chế delegation. Đừng mặc định có thể chuyển các JAR từ classpath sang module path mà giữ nguyên các package trùng.

Không có một cờ JVM nào tự động giải quyết mọi trường hợp split package. Cần xác định lỗi nằm ở **đồ thị đọc module** hay **cách định nghĩa lớp vào class loader** trước khi chọn cách sửa.

## 10. Câu hỏi tự kiểm tra

1. Hai module ở hai layer khác nhau cùng chứa `com.example.util`: có nhất thiết lỗi không? **Không**; xét thêm cấu hình và loader.
2. Hai module chứa cùng package và được gán một loader: có hợp lệ không? **Không**, với named modules việc định nghĩa layer sẽ gặp xung đột.
3. `defineModulesWithManyLoaders` có sửa lỗi consumer đọc hai module cùng export một package không? **Không**; lỗi resolution vẫn có thể xảy ra.
4. Hai class có tên `demo.plugin.impl.Greeter` nhưng loader khác nhau có phải cùng kiểu không? **Không**.
5. Muốn truyền dữ liệu an toàn giữa hai plugin layer nên làm gì? **Dùng interface/DTO từ module API chung ở layer cha**, hoặc chuyển dữ liệu qua dạng trung gian như JSON nếu muốn cô lập hoàn toàn.

## 11. Ghi nhớ

Trong JPMS, một split package có thể là lỗi ở **resolution**, ở **ánh xạ loader khi tạo layer**, hoặc là nguồn gây nhầm lẫn **định danh kiểu khi chạy**. Tách plugin thành các `ModuleLayer` với loader riêng có thể cho phép trùng tên package, nhưng không làm hai lớp cùng tên trở thành cùng một lớp. Thiết kế ổn định nhất là giữ API dùng chung ở layer cha và cô lập phần triển khai ở các layer con.
