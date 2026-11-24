# Lấy hợp đồng từ vị trí hoặc artifact ngoài dự án

## Mục tiêu học tập

Trong **Spring Cloud Contract**, producer cung cấp API hoặc phát thông điệp, còn consumer sử dụng giao diện đó. Hợp đồng **Groovy/YAML DSL** mô tả hành vi HTTP hoặc messaging; từ DSL, công cụ sinh **producer contract tests**, **stub** cho consumer chạy bằng **Stub Runner**, và giúp CI phát hiện thay đổi không tương thích.

Bài thuộc chương **Kho hợp đồng và artifact**, tập trung vào tình huống hợp đồng **không nằm ngay trong module producer**. Chúng có thể được lưu trong thư mục khác, đóng gói thành **contract JAR** trên Nexus/Artifactory hoặc đặt trong **Git SCM repository**.

Sau bài học, bạn có thể:

- Phân biệt **contract source**, **contract definition JAR**, **producer binary** và **producer stubs JAR**.
- Chỉ định thư mục hợp đồng ngoài module bằng `contractsDirectory` (Maven) hoặc `contractsDslDir` (Gradle).
- Cấu hình producer tải contract artifact với `contractDependency`, `contractsPath`, `contractsMode` và URL repository.
- Tải hợp đồng qua Git SCM với tiền tố `git://` và hiểu cấu trúc `META-INF/group/artifact/version/contracts`.
- Chọn đúng contract cho từng producer/consumer và giữ version có thể truy vết.
- Kết nối việc lấy DSL với generated producer tests, stub publication, consumer Stub Runner và CI.
- Tránh build xanh giả do 0 generated tests, artifact cũ, sai đường dẫn, skip test hoặc caching.

> **Nguyên tắc:** kho hợp đồng chỉ cung cấp định nghĩa kỳ vọng. Producer vẫn phải chạy **generated tests trên implementation thật và đạt** trước khi công bố stub như một giao diện đã xác nhận.

## 1. Vì sao cần contract repository độc lập?

Giả sử **Inventory Service** cung cấp API cho **Checkout Service**:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

Khi hai đội quản lý các repository riêng, Checkout có thể không được quyền clone source code Inventory. Nhưng Checkout cần đề xuất hợp đồng, review body/status/header và biết liệu producer đã hỗ trợ API hay chưa. Một kho chung có thể:

1. Cho consumer gửi pull request mô tả hành vi họ cần.
2. Cho producer review kỳ vọng trước khi sửa code.
3. Cho nhiều consumer cùng nhìn thấy yêu cầu của mình.
4. Phát hành contract definitions thành một version độc lập.
5. Cho producer CI tải **đúng phiên bản đã được review**.
6. Cho consumer test dựa trên stub mà producer đã xác minh.

**Đánh đổi:** khi nguồn DSL nằm ngoài module, build phụ thuộc thêm vào repository URL, credentials, layout JAR/Git, version và cache. Nếu chúng sai, producer có thể không kiểm chứng thay đổi mới dù build vẫn báo SUCCESS.

### Luồng tổng thể

~~~mermaid
flowchart TD
    A["Consumer đề xuất Groovy/YAML DSL"] --> B["Contract repository"]
    B --> C{"Nguồn tải"}
    C -->|Folder| D["Local directory"]
    C -->|Artifact| E["Maven contract JAR"]
    C -->|Git| F["Git SCM tree"]
    D --> G["Producer contract generator"]
    E --> G
    F --> G
    G --> H["Generated producer tests"]
    H --> I{"Producer implementation PASS?"}
    I -->|Không| X["Chặn verified stub"]
    I -->|Có| J["Producer :stubs artifact"]
    J --> K["Consumer Stub Runner"]
    K --> L["Consumer test client/handler thật"]
~~~

## 2. Bốn loại tài nguyên không được nhầm

| Tài nguyên | Tọa độ hoặc tên mẫu | Vai trò |
|---|---|---|
| **DSL source** | `stockAvailable.groovy`, `stockAvailable.yml` | Mô tả hành vi giao tiếp |
| **Contract definition JAR** | `com.example.contracts:shared-contracts:1.4.0` | Đóng gói DSL/fixtures để producer tải |
| **Producer binary** | `com.example:inventory-producer:2.3.0` | Ứng dụng Inventory thực |
| **Producer stub JAR** | `com.example:inventory-producer:2.3.0:stubs` | Mappings/definitions mà consumer dùng với Stub Runner |

**Contract JAR không phải stub JAR.** Contract JAR có thể được công bố từ repository hợp đồng trước khi producer hoàn thiện hành vi; verified stub phải gắn với producer tests đã chạy và PASS. Hai artifact có thể có **version khác nhau**:

~~~text
Contract definitions: com.example.contracts:shared-contracts:1.4.0
Producer artifact:    com.example:inventory-producer:2.3.0
Consumer stubs:       com.example:inventory-producer:2.3.0:stubs
~~~

CI cần lưu liên kết: **producer 2.3.0 đã kiểm chứng với shared-contracts 1.4.0 từ source SHA nào**, rồi tạo `:stubs` mang digest nào.

Thêm contract JAR vào `implementation` của Gradle hoặc `dependencies` runtime của Maven **không tự hướng dẫn generator** đọc DSL. Spring Cloud Contract plugin có cấu hình riêng cho nguồn hợp đồng.

## 3. Một DSL mẫu dùng ở mọi nguồn

### Groovy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Ton kho SKU-101 con 8 san pham'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

### YAML tương đương

~~~yaml
description: 'Ton kho SKU-101 con 8 san pham'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    available: true
    quantity: 8
~~~

Chọn **một** định dạng cho tình huống này trong build thực tế. Giá trị `quantity: 8` là number và `available: true` là boolean; không nên sửa thành string chỉ để làm producer test xanh nếu consumer yêu cầu đúng kiểu.

## 4. Các nguồn contract và lựa chọn phù hợp

| Nguồn | Ví dụ | Producer sử dụng | Phù hợp |
|---|---|---|---|
| Folder local ngoài module | `../api-contracts/inventory` | `contractsDirectory` / `contractsDslDir` | Mono-repo, CI checkout hai repo |
| Maven artifact repository | `shared-contracts:1.4.0` | `contractDependency` + repository + `contractsPath` | Artifact có version, nhiều pipeline |
| Git SCM repository | `git://https://git.example.invalid/team/contracts.git` | SCM downloader + tọa độ producer | Git review và SCM stubs |

**Lưu ý:** Maven repository và Git repository không phải hai cách đặt URL tương đương. Maven giải quyết JAR theo `group:artifact:version`; Git SCM downloader tra cây file có bố cục riêng. Đừng áp dụng layout của nguồn này cho nguồn kia.

## 5. Cách A — Thư mục contract nằm ngoài module producer

Một workspace mẫu:

~~~text
commerce-workspace/
├── api-contracts/
│   └── inventory/
│       └── stockAvailable.groovy
└── inventory-producer/
    ├── pom.xml
    ├── build.gradle
    └── src/main/java/...
~~~

`api-contracts` có thể được lưu trong mono-repo hoặc do CI checkout một repository khác vào cùng workspace.

### Maven: contractsDirectory

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_SCC_VERSION</version>
      <extensions>true</extensions>
      <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
          com.example.inventory.contract.InventoryContractBase
        </baseClassForTests>
        <contractsDirectory>
          ${project.basedir}/../api-contracts/inventory
        </contractsDirectory>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`contractsDirectory` là **đường dẫn filesystem**, không phải tọa độ Maven. Maven không tự clone Git chỉ vì khai báo path ngoài dự án. Pipeline phải checkout repository và đảm bảo folder tồn tại trước khi chạy verifier.

`REPLACE_WITH_COMPATIBLE_SCC_VERSION` là placeholder cần thay. Module producer còn cần Spring Boot, verifier dependencies và base class thực.

### Gradle: contractsDslDir

~~~groovy
contracts {
    testFramework = 'JUNIT5'
    testMode = 'MockMvc'
    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'

    contractsDslDir = file('../api-contracts/inventory')
}
~~~

Khi dùng Gradle plugin hiện đại, contract local thường nằm ở `src/contractTest/resources/contracts`. `contractsDslDir` override nơi plugin tìm DSL; path tương đối được giải quyết theo module Gradle đang cấu hình.

### Ưu điểm và giới hạn

- **Ưu điểm:** dễ thử contract PR chưa publish, không cần registry, có thể xem diff trực tiếp.
- **Giới hạn:** CI cần workspace layout ổn định; không tự pin commit, có nguy cơ folder trống hoặc sai revision.
- **Cách bảo vệ:** checkout commit/tag xác định của contract repo, log revision, kiểm tra số DSL và số generated producer tests thực sự chạy.

Không chỉ xác minh “folder tồn tại”. Một folder rỗng hoặc chứa hợp đồng của producer khác vẫn có thể dẫn tới **0 test có ý nghĩa**.

## 6. Cách B — Đóng gói contract JAR dùng chung

Một repository độc lập:

~~~text
shared-contracts/
├── pom.xml hoặc build.gradle
└── src/main/resources/
    └── com/example/
        ├── inventory-producer/
        │   ├── checkout-consumer/
        │   │   └── stockAvailable.groovy
        │   └── reporting-consumer/
        │       └── stockLow.yml
        └── pricing-producer/
            └── checkout-consumer/
                └── priceAvailable.groovy
~~~

JAR tạo ra các entry:

~~~text
com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
com/example/inventory-producer/reporting-consumer/stockLow.yml
com/example/pricing-producer/checkout-consumer/priceAvailable.groovy
~~~

Tọa độ artifact:

~~~text
com.example.contracts:shared-contracts:1.4.0
~~~

Cấu trúc theo tên consumer giúp người review biết consumer nào phụ thuộc từng contract; nó cũng hỗ trợ cách tổ chức `stubs-per-consumer` khi được cấu hình đầy đủ.

### Maven contract definitions module

Với `src/main/resources`, Maven jar packaging có thể rất gọn:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.contracts</groupId>
  <artifactId>shared-contracts</artifactId>
  <version>1.4.0</version>
  <packaging>jar</packaging>
</project>
~~~

~~~bash
# Build contract JAR ở repository hợp đồng.
./mvnw -B -ntp package
jar tf target/shared-contracts-1.4.0.jar
~~~

Kiểm tra phải nhìn thấy DSL dưới `com/example/inventory-producer`. Thành công trong việc **đóng gói JAR** chưa chứng minh producer triển khai đúng interface.

### Gradle contract JAR module

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
}

group = 'com.example.contracts'
version = '1.4.0'

publishing {
    publications {
        definitions(MavenPublication) {
            from components.java
            artifactId = 'shared-contracts'
        }
    }
}
~~~

`java` plugin đưa `src/main/resources` vào JAR. Đây là publication **định nghĩa hợp đồng**, khác với `verifierStubsJar` của producer. Repository và credentials cần được cấu hình an toàn khi phát hành thật.

### Ba ranh giới kiểm tra

| Bước | Trách nhiệm |
|---|---|
| Contract repo CI | Review DSL, syntax, fixtures và đóng gói JAR đúng cấu trúc |
| Producer CI | Tải contract JAR, sinh/chạy tests với code Inventory thật |
| Consumer CI | Tải **producer stubs**, kiểm tra client/handler thật qua Stub Runner |

**Contract artifact tồn tại không có nghĩa producer contract tests đã đạt.**

## 7. Producer Maven tải contract JAR bằng REMOTE

Giả sử JAR `com.example.contracts:shared-contracts:1.4.0` được publish trong một Maven-compatible repository.

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_SCC_VERSION</version>
      <extensions>true</extensions>

      <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
          com.example.inventory.contract.InventoryContractBase
        </baseClassForTests>

        <contractsMode>REMOTE</contractsMode>
        <contractsRepositoryUrl>
          https://repo.example.invalid/repository/contract-definitions
        </contractsRepositoryUrl>

        <contractDependency>
          <groupId>com.example.contracts</groupId>
          <artifactId>shared-contracts</artifactId>
          <version>1.4.0</version>
        </contractDependency>

        <contractsPath>com/example/inventory-producer</contractsPath>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Repository `example.invalid` là URL **minh họa không hoạt động**; phải thay bằng Nexus/Artifactory/Maven repository của dự án. Các dependencies verifier, Spring Boot BOM và test setup không được rút gọn thành một POM hoàn chỉnh ở đây.

| Option | Nghĩa |
|---|---|
| `contractsMode=REMOTE` | Resolver tải hợp đồng từ nguồn remote |
| `contractsRepositoryUrl` | URL Maven repository chứa contract JAR |
| `contractDependency` | Chỉ định artifact chứa DSL |
| `contractsPath` | Thư mục **bên trong JAR** dành cho Inventory |
| `baseClassForTests` | Class chuẩn bị controller/application producer thật |
| `testFramework` | Chọn JUnit 5 trong ví dụ |

### Vì sao contractsPath quan trọng?

Mặc định `contractsPath` được tài liệu mô tả là suy từ `groupId/artifactId` của **contract dependency**:

~~~text
Contract artifact:
  com.example.contracts:shared-contracts:1.4.0

Default path inferred:
  com/example/contracts/shared-contracts

Actual contracts path in our JAR:
  com/example/inventory-producer
~~~

Nếu bỏ `contractsPath`, plugin có thể **download artifact thành công nhưng không tìm thấy contract**. Sự khác biệt giữa resolve JAR và discover DSL là một nguồn build xanh giả rất phổ biến.

Maven có thể sử dụng các repositories đã cấu hình nếu `contractsRepositoryUrl` không khai báo, tùy phiên bản plugin. Khi CI yêu cầu truy vết, nên biết rõ **repository và artifact digest** đã được sử dụng.

## 8. Producer Gradle tải cùng contract JAR

Trong `inventory-producer/build.gradle` đã áp dụng plugin `org.springframework.cloud.contract`:

~~~groovy
contracts {
    testFramework = 'JUNIT5'
    testMode = 'MockMvc'
    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'

    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractRepository {
        repositoryUrl =
            'https://repo.example.invalid/repository/contract-definitions'
    }

    contractsPath = 'com/example/inventory-producer'
}
~~~

Đây là **khối cấu hình contracts**, không phải toàn bộ build file. Cần plugin version, BOM, verifier dependencies và base test phù hợp với Spring Boot/Cloud đang dùng.

Có thể khai báo dependency bằng field thay vì `stringNotation`:

~~~groovy
contractDependency {
    groupId = 'com.example.contracts'
    artifactId = 'shared-contracts'
    version = '1.4.0'
}
~~~

Chọn **một cách khai báo**; không đặt version khác nhau ở hai nơi.

### Kiểm tra Gradle tasks

~~~bash
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
~~~

Với Gradle plugin hiện đại, generated producer tests thường chạy trong source set/task `contractTest`. Test phải gọi Inventory code thật, không phải một stub giả lập endpoint Inventory.

Đừng dùng:

~~~groovy
// Không thay cho cấu hình contractDependency:
implementation 'com.example.contracts:shared-contracts:1.4.0'
~~~

vì `implementation` quản lý classpath ứng dụng chứ không chỉ vị trí DSL cho generator.


## 9. LOCAL và REMOTE: cùng contract, nguồn khác nhau

Khi đang phát triển contract candidate chưa publish, đội contract có thể build JAR rồi cài vào local Maven repository:

~~~bash
# Chạy trong repository shared-contracts.
./mvnw -B -ntp clean install
~~~

Producer có thể dùng `contractsMode=LOCAL` với cùng tọa độ:

~~~xml
<configuration>
    <contractsMode>LOCAL</contractsMode>
    <contractDependency>
        <groupId>com.example.contracts</groupId>
        <artifactId>shared-contracts</artifactId>
        <version>1.4.0</version>
    </contractDependency>
    <contractsPath>com/example/inventory-producer</contractsPath>
</configuration>
~~~

Gradle tương đương:

~~~groovy
contracts {
    contractsMode = 'LOCAL'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractsPath = 'com/example/inventory-producer'
}
~~~

**LOCAL không có nghĩa plugin đọc trực tiếp từ `target/shared-contracts-1.4.0.jar`**; artifact phải được cài vào Maven local repository mà process build sử dụng, với metadata phù hợp.

| Thuộc tính | LOCAL | REMOTE |
|---|---|---|
| Nguồn artifact | Maven local repo | Nexus/Artifactory/Maven-compatible repo |
| Phù hợp | Dev offline, thử PR, CI candidate được install riêng | CI, release, nhiều team cùng tiêu thụ |
| Rủi ro | Cache cũ cùng version, máy dev thiếu artifact | Network, credentials, proxy, repository cache |
| Kiểm soát | Log path + version/digest local | Log repository URL + version/digest |
| Tự kiểm chứng producer? | **Không** | **Không** |

**Phân biệt tên cấu hình:**

- `contractsMode`: **producer** lấy *contract definitions* ở LOCAL/REMOTE.
- `stubsMode`: **consumer Stub Runner** lấy *producer stubs* ở LOCAL/REMOTE.

Chúng có cùng tên giá trị nhưng tải **hai loại artifact khác nhau**.

## 10. Cách C — Dùng Git SCM làm contract repository

Spring Cloud Contract mô tả cách dùng Git làm SCM store cho contract và stubs. Để plugin chọn đúng SCM downloader, URL phải có **tiền tố `git://`**:

~~~text
git://https://git.example.invalid/team/service-contracts.git
~~~

So với một URL HTTPS thông thường:

~~~text
https://git.example.invalid/team/service-contracts.git
~~~

tiền tố `git://` là **quy ước chọn resolver của Spring Cloud Contract**, đặt trước transport URL HTTPS. Không hiểu lầm rằng người dùng phải kết nối tới một Git daemon không mã hóa.

### Layout SCM mà downloader mong đợi

~~~text
service-contracts.git/
└── META-INF/
    └── com.example/
        └── inventory-producer/
            └── 2.3.0/
                ├── contracts/
                │   └── checkout-consumer/
                │       ├── stockAvailable.groovy
                │       └── stockNotFound.yml
                └── mappings/
                    └── checkout-consumer/
                        └── stockAvailable.json
~~~

Theo tài liệu Git SCM, root của mỗi producer/version là:

~~~text
META-INF/<groupId>/<artifactId>/<version>/
~~~

trong đó có `contracts/` chứa DSL và `mappings/` dành cho HTTP stub mappings. Ở ví dụ, group ID `com.example` được dùng nguyên như một folder sau `META-INF`. Đây là **layout của SCM downloader**, khác `com/example/inventory-producer` nằm trong contract JAR ở phần trước.

Trong chu trình CDC, consumer có thể đề xuất DSL trước, còn `mappings` sẽ được bổ sung **sau khi producer sinh và kiểm chứng stubs**. Không yêu cầu mọi PR contract mới đã có mapping JSON.

### Maven cấu hình Git remote

Trong Maven plugin producer:

~~~xml
<configuration>
    <contractsMode>REMOTE</contractsMode>

    <contractsRepositoryUrl>
        git://https://git.example.invalid/team/service-contracts.git
    </contractsRepositoryUrl>

    <contractDependency>
        <groupId>com.example</groupId>
        <artifactId>inventory-producer</artifactId>
        <version>2.3.0</version>
    </contractDependency>

    <baseClassForTests>
        com.example.inventory.contract.InventoryContractBase
    </baseClassForTests>
</configuration>
~~~

`contractDependency` ở trường hợp SCM được dùng để tìm đường dẫn `META-INF/com.example/inventory-producer/2.3.0/contracts`. Nó **không có nghĩa repository Git chứa một contract JAR Maven**.

### Gradle cấu hình Git remote

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example:inventory-producer:2.3.0'
    }

    contractRepository {
        repositoryUrl =
            'git://https://git.example.invalid/team/service-contracts.git'
    }

    baseClassForTests =
        'com.example.inventory.contract.InventoryContractBase'
}
~~~

Các đoạn trên là phần cốt lõi của plugin. Producer vẫn cần dependency/test setup và Git authentication phù hợp, không đặt password/token trực tiếp trong source hoặc URL.

### Có tự động push stubs ngược lên Git không?

**Không.** Spring Cloud Contract có goal/task `pushStubsToScm` nhưng việc bật nó phải **có chủ đích**, ví dụ:

~~~bash
./gradlew :inventory-producer:pushStubsToScm
~~~

Đây là thao tác **ghi vào kho ngoài**, không cần để tải contract. Nên chỉ gọi sau khi generated producer tests **thực sự chạy và PASS**, và trong CI job có quyền push được bảo vệ.

Với Maven có goal `pushStubsToScm` tương ứng; không tự gắn nó vào mọi PR chưa review rồi coi việc push thành công là producer verification.

## 11. Version folder của Git không thay thế Git commit

Ví dụ SCM dùng `META-INF/com.example/inventory-producer/2.3.0/contracts`. “`2.3.0`” chỉ là **version folder logic**; nếu branch mặc định của Git còn thay đổi, nội dung thư mục đó có thể bị sửa sau lần producer kiểm thử.

Cần quản lý hai lớp định danh:

1. **Logical version:** version folder / contract artifact version mà plugin tìm.
2. **Source revision:** commit SHA/tag hoặc digest JAR thực sự đã được kiểm chứng.

Muốn tái lập chặt chẽ:

- Tạo **contract JAR version bất biến** từ Git commit đã review.
- Hoặc checkout repo Git tới một **commit SHA/tag cố định** trong CI, rồi dùng thư mục local `contractsDirectory`/`contractsDslDir` của snapshot ấy.
- Nếu muốn SCM downloader pin revision trực tiếp, kiểm tra khả năng và tên option của **phiên bản plugin đang dùng**; không tự tạo property `gitCommit` hoặc `branch`.
- Lưu contract SHA cùng producer SHA, phiên bản stub và kết quả generated tests.

Không âm thầm sửa DSL dưới một version đã phát hành mà vẫn giữ cùng version để các pipeline sử dụng cache khác nhau.

## 12. Chọn contract cho từng producer và consumer

Một contract JAR có thể chứa:

~~~text
com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
com/example/inventory-producer/reporting-consumer/stockLow.groovy
com/example/pricing-producer/checkout-consumer/priceAvailable.groovy
~~~

Nếu Inventory producer dùng:

~~~groovy
contracts {
    contractsPath = 'com/example/inventory-producer'
}
~~~

nó chọn nhóm hợp đồng Inventory. Để lọc thêm theo consumer, Spring Cloud Contract cung cấp các cơ chế như `includedFiles`, `ignoredFiles` tùy plugin; filter phải match **đường dẫn thực bên trong artifact đã giải nén**.

### Ví dụ Maven includedFiles

~~~xml
<configuration>
    <contractsPath>com/example/inventory-producer</contractsPath>
    <includedFiles>
        <includedFile>**/checkout-consumer/**</includedFile>
        <includedFile>**/reporting-consumer/**</includedFile>
    </includedFiles>
</configuration>
~~~

Đây là phần minh họa thêm vào `contractDependency`/`contractsMode` của module producer, không phải cấu hình hoàn chỉnh. Nếu path hoặc pattern sai, artifact vẫn có thể được download nhưng **0 contract được chọn**.

### Khi HTTP và messaging dùng chung một JAR

- HTTP: generated tests cần base class dựng đúng controller/MockMvc hoặc ứng dụng qua HTTP.
- Messaging: generated tests cần messaging verifier/binder, `triggeredBy` hoặc `messageFrom` và destination.
- Security/error cases: có thể cần test setup với exception handler/filter hoặc fixture đặc biệt.

Spring Cloud Contract có `baseClassMappings` cho các contract path/package patterns. Mỗi nhóm phải kế thừa đúng base class; không mặc định mọi test có thể chạy với cùng một setup rồi bỏ qua những nhánh khó.

### Lỗi mapping chồng lấn

Nếu hai contract cùng match `GET /api/inventory/SKU-101` nhưng trả hai response khác nhau, việc chúng nằm trong folder của hai consumer **không tự làm WireMock phân biệt request**. Cần sửa matcher, versioning, URL hoặc chính sách stub-per-consumer phù hợp thay vì hy vọng folder quyết định ưu tiên runtime.

## 13. Consumer đề xuất hợp đồng qua repository chung

Quy trình CDC thường có các bước:

~~~mermaid
sequenceDiagram
    participant C as Checkout team
    participant R as Contract repository
    participant P as Inventory producer CI
    participant A as Artifact registry
    participant T as Checkout consumer CI
    C->>R: PR bổ sung/sửa Groovy hoặc YAML DSL
    R->>R: Review interface, fixture và ownership
    P->>R: Lấy đúng contract candidate revision
    P->>P: Sinh tests, triển khai, verify producer
    alt Producer tests đạt
        R->>A: Publish contract artifact theo policy
        P->>A: Publish candidate producer :stubs
        T->>A: Stub Runner tải đúng version
        T->>T: Kiểm tra client/handler consumer thật
    else Producer test lỗi
        P-->>C: Phối hợp sửa contract/implementation
    end
~~~

Repository hợp đồng là nơi **consumer đề xuất yêu cầu**; producer phải chấp nhận và chứng minh implementation đáp ứng.

### Producer PASS chưa đồng nghĩa mọi consumer cũ còn tương thích

Contract cũ:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

Contract mới:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

Nếu implementation producer và DSL được đổi cùng lúc, generated tests mới có thể PASS. Nhưng Checkout cũ vẫn đọc `available` và `quantity`.

Cần chạy consumer tests với **candidate stub mới** và review breaking changes đối với các phiên bản đang triển khai. Đây là lý do contract repository nên lưu owner/consumer context, không chỉ danh sách DSL file.

## 14. Producer verification không thay đổi vì DSL nằm xa hơn

Sau khi giải quyết nguồn contract:

~~~text
Contract folder / contract JAR / Git SCM
    |
    v
Discover Groovy/YAML contract files
    |
    v
Generate producer test sources
    |
    v
Compile and run generated tests with real producer code
    |
    v
Assert HTTP status/headers/body or message payload
    |
    v
PASS => producer stub eligible for publication
~~~

### Maven

~~~bash
./mvnw -B -ntp clean verify
~~~

Generated test thường ở `target/generated-test-sources/contracts` nhưng có thể tùy chỉnh.

### Gradle

~~~bash
./gradlew :inventory-producer:contractTest
~~~

Generated tests thường nằm trong vùng `build/generated-test-sources/contractTest`, tùy plugin version.

### Đọc những bằng chứng nào?

1. Resolver tải đúng artifact version/revision và repository dự định.
2. `contractsPath`/SCM folder khớp và phát hiện đúng số DSL.
3. Generated tests được biên dịch, **thực sự chạy** và có test report.
4. Base class gọi code producer, không chỉ một stub trả response mẫu.
5. Assertions kiểm tra field/status/header/payload mà consumer phụ thuộc.
6. Tests PASS, rồi mới đóng gói/publish verified producer `:stubs`.

`failOnNoContracts` và `failOnInProgress` là những tùy chọn hữu ích để fail closed. Ví dụ Gradle:

~~~groovy
contracts {
    failOnNoContracts = true
    failOnInProgress = true
}
~~~

Kiểm tra option/default theo version plugin và vẫn phải xác nhận **test count**: tùy chọn fail khi thiếu contract không thay thế bằng chứng test đã chạy.

## 15. Contract source chỉ là build-time input

Một cách viết dễ sai:

~~~groovy
dependencies {
    // Không có nghĩa Contract Verifier tự đọc đúng DSL path.
    implementation 'com.example.contracts:shared-contracts:1.4.0'
}
~~~

Nếu mục tiêu là lấy contract JAR để sinh test, phải dùng:

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractsPath = 'com/example/inventory-producer'
}
~~~

Cần thêm repository URL phù hợp. Không đưa hợp đồng vào runtime classpath chỉ vì chưa cấu hình plugin đúng.

Tách rành mạch:

- Contract DSL: **input của build/test**.
- Generated producer test: **kiểm chứng producer implementation**.
- Stub artifact: **đầu vào test của consumer**.
- Runtime producer: **ứng dụng thực**, không cần contract JAR chỉ để phục vụ HTTP.

## 16. Consumer Stub Runner nhận producer :stubs, không nhận contract JAR

Sau khi producer đã verify:

~~~text
Contract source:
  com.example.contracts:shared-contracts:1.4.0

Verified producer:
  com.example:inventory-producer:2.3.0

Verified producer stub:
  com.example:inventory-producer:2.3.0:stubs
~~~

Consumer dùng Stub Runner tải **producer stub**, ví dụ:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.invalid/repository/verified-stubs"
)
class CheckoutInventoryContractTest {
    // Dùng HTTP client thật của Checkout, trỏ tới runtime stub port.
    // Assert JSON/status và quyết định nghiệp vụ.
}
~~~

Đây là skeleton; Spring test phải có client, cách nhận port qua `@StubRunnerPort`/`StubFinder` và assertion tương ứng. `example.invalid` là placeholder.

**Không** trỏ Stub Runner vào `com.example.contracts:shared-contracts:1.4.0` và coi đó là stub đã được producer xác nhận.

### Ba repository URL có vai trò khác nhau

| Nơi cấu hình | Ý nghĩa |
|---|---|
| Producer Maven `contractsRepositoryUrl` | Tải **contract definitions** |
| Producer Gradle `contractRepository.repositoryUrl` | Tải **contract definitions** |
| Consumer Stub Runner `repositoryRoot` | Tải **producer stub artifacts** |

Một tổ chức có thể dùng chung một Nexus/Artifactory instance, nhưng nên biết rõ path, permission và artifact đang được tải ở từng bước.

Với HTTP, client phải gọi đúng URL/cổng Stub Runner, không gọi `localhost:0` hoặc producer production. Với messaging, consumer dùng `StubTrigger` và chờ kết quả xử lý; contract JAR không tự tạo broker hay listener.


## 17. Version và cache: những cách tạo build xanh giả

### Tình huống A — Contract đã publish bản mới, producer vẫn dùng bản cũ

~~~text
Contract repository:
  shared-contracts 1.4.1

Producer build:
  contractDependency = shared-contracts:1.4.0

Build result:
  PASS
~~~

PASS chỉ xác nhận implementation đáp ứng **1.4.0**, không nói gì về các yêu cầu mới trong 1.4.1.

### Tình huống B — Cùng version nhưng bytes artifact bị thay

~~~text
Yesterday: shared-contracts:1.4.0 = bytes A
Today:     shared-contracts:1.4.0 = bytes B
~~~

Hai runner có thể cache khác nhau và đều báo cùng version, dẫn đến khó tái lập. Với release, cần **version bất biến**. Với candidate PR, tạo version riêng theo build/commit hoặc kiểm soát digest.

### Tình huống C — Producer mới, consumer vẫn dùng stub cũ

~~~text
Producer verifies:
  shared-contracts:1.4.1

Consumer Stub Runner loads:
  inventory-producer:2.2.0:stubs

Expected candidate producer:
  inventory-producer:2.3.0:stubs
~~~

Consumer test vẫn có thể xanh vì đang dùng phiên bản chưa phản ánh thay đổi. Cần log **artifact thực tế Stub Runner resolve**, không chỉ log version mong muốn.

### Tình huống D — Build cache của Gradle che mất việc test chưa chạy

Một Gradle test task có thể được báo `UP-TO-DATE` hoặc lấy từ build cache khi inputs/outputs không phản ánh thay đổi contract artifact ngoài. Nếu CI đang kiểm tra candidate nhạy cảm, có thể chạy lại:

~~~bash
./gradlew :inventory-producer:contractTest --rerun-tasks --no-build-cache
~~~

Đây là biện pháp chẩn đoán/ngắn hạn. Về lâu dài, cần khai báo task inputs phù hợp, version artifact bất biến và một pipeline chủ động kiểm tra **test count + pass/fail**.

### Tình huống E — Wildcard/latest đổi nghĩa giữa các lần build

Một số tài liệu cũ minh họa version `+`/`latest` để lấy bản mới. Trong CI làm quality gate, chúng khiến kết quả phụ thuộc vào thời điểm resolve và cache.

Thay:

~~~xml
<version>+</version>
~~~

bằng một phiên bản cụ thể:

~~~xml
<version>1.4.1</version>
~~~

và ghi digest/source SHA đã dùng. Với `SNAPSHOT` mutable, cô lập cache hoặc tạo candidate ID duy nhất để tránh cross-build contamination.

## 18. Credentials, quyền và an toàn của kho contract

Kho hợp đồng thường được chia sẻ giữa nhiều nhóm. Nên tách quyền:

| Tác nhân | Quyền hợp lý | Quyền nên tránh |
|---|---|---|
| Producer CI | **Đọc** contract JAR/Git revision được duyệt | Ghi mọi contract repository |
| Contract repository CI | Publish contract JAR sau review | Overwrite artifact release |
| Consumer CI | Đọc **producer stub** đã phát hành/candidate được cấp | Release credentials |
| Producer release job | Publish verified stub sau quality gate | Push bản chưa test |
| Reviewer | Review DSL/fixtures và danh sách consumer bị ảnh hưởng | Cho phép merge chỉ vì packaging xanh |

### Credentials và proxy

Maven plugin có các option dành cho repository username/password và proxy; Gradle có `contractRepository` với field `username`, `password`, `proxyHost`, `proxyPort` theo tài liệu.

Khi sử dụng:

- Lấy giá trị từ **CI secret manager** hoặc credential provider, không hardcode trong `pom.xml`/`build.gradle`.
- Chỉ cấp quyền đọc cần thiết cho build thông thường; job phát hành có quyền ghi riêng.
- Không truyền token dưới dạng URL được commit vào Git.
- Không in URL có credential hoặc nội dung nhạy cảm ra log.
- Kiểm tra TLS/CA/proxy của môi trường CI; việc máy dev tải được artifact không chứng minh container CI có thể tải.
- Không dùng dữ liệu người dùng thật trong contract fixtures.

### Governance Git SCM

- Bảo vệ nhánh chính; có code owners/reviewers theo producer.
- Mỗi PR mô tả consumer nào cần thay đổi.
- Review status, header, URL, MIME, body field types và messaging destinations.
- Không tự kích hoạt `pushStubsToScm` trên PR không tin cậy.
- Chỉ cho phép producer CI push mappings khi generated tests PASS.
- Ghim commit/tag hoặc đóng gói contract JAR versioned để CI tái lập.

Một repository riêng không tự tạo ra trách nhiệm sở hữu; quy trình review mới làm điều đó.

## 19. Troubleshooting: tìm sai ở source, discovery hay verification?

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Cannot resolve contractDependency` | Sai group/artifact/version, URL, credentials | Kiểm tra repository, tọa độ, quyền đọc và log resolver |
| Contract JAR tải được nhưng 0 test | `contractsPath` sai, include filter loại hết | Dùng `jar tf`, kiểm tra nested DSL path và số contract |
| Maven vẫn tìm folder mặc định | Cấu hình plugin không ở module/phase đúng | Đọc effective POM/plugin log |
| Gradle không thấy `contractTest` | Plugin chưa áp dụng hoặc version task khác | `./gradlew :inventory-producer:tasks --all` |
| Test sinh nhưng không compile | Base class sai package/JUnit, thiếu verifier dependency | Đọc generated test/imports, sửa base class |
| Generated test trả 404 | Controller/fixture/path không khớp | Kiểm tra test mode, MockMvc/context và request |
| Messaging receive timeout | Trigger không publish hoặc binder/destination sai | Xem `triggeredBy`, `messageFrom`, `sentTo` và adapter |
| Git không lấy contract | Thiếu `git://`, URL/credentials sai | Kiểm tra SCM resolver và Git logs |
| Git clone được nhưng 0 DSL | Layout `META-INF/group/artifact/version/contracts` sai | Đối chiếu tree và `contractDependency` |
| Stub Runner tìm thấy contract JAR nhưng không có stub | Nhầm definitions JAR với producer `:stubs` | Publish producer stub đúng classifier/version |
| Consumer nhận WireMock 404 | Request không match mapping | Kiểm tra URL/header/body và unmatched request log |
| CI xanh với contract cũ | Cache version mutable, pinned version chưa nâng | Log source SHA/digest, kiểm tra resolved artifact |
| Push mappings không xảy ra | Chưa gọi `pushStubsToScm` | Chỉ gọi trong release job sau verification |
| Published stub khác với source đã test | Rebuild từ commit khác hoặc dùng artifact cũ | Ghim SHA/digest và chuyển đúng candidate artifact |

### Trình tự debug hiệu quả

1. **Source:** contract nằm ở local folder, Maven JAR hay Git? Tải đúng version/SHA chưa?
2. **Discovery:** sau khi tải, plugin tìm được những DSL files nào? `contractsPath` có đúng không?
3. **Verification:** generated tests có thực sự chạy với producer code và PASS không?
4. **Packaging:** stub artifact có đúng mappings/contract/fixture và classifier `stubs` không?
5. **Consumption:** consumer Stub Runner tải artifact nào và client thật gọi URL nào?

Đừng sửa matcher hoặc tăng timeout khi nguyên nhân thật là **không tải được DSL**. Cũng đừng đổi sang `latest` để che lỗi versioning.

## 20. Quy trình CI hai repository và hai artifact

Một pipeline tham khảo:

~~~mermaid
flowchart TD
    A["PR sửa DSL ở contract repo"] --> B["Review + kiểm tra DSL/fixture"]
    B --> C["Đóng gói candidate contract JAR"]
    C --> D["Ghi artifact version + contract SHA"]
    D --> E["Producer CI tải đúng candidate"]
    E --> F["Sinh/chạy generated producer tests"]
    F --> G{"Producer PASS?"}
    G -->|Không| H["Không publish verified stub"]
    G -->|Có| I["Đóng gói candidate producer :stubs"]
    I --> J["Consumer Stub Runner dùng đúng stub"]
    J --> K{"Consumer compatibility PASS?"}
    K -->|Không| L["Review breaking change/migration"]
    K -->|Có| M["Release theo chính sách"]
~~~

### Một báo cáo có thể truy vết

~~~text
Contract source SHA:        <contract-sha>
Contract artifact:          com.example.contracts:shared-contracts:1.4.1
Contract JAR SHA-256:       <digest-A>

Producer source SHA:        <producer-sha>
Generated producer tests:   8 executed / 8 passed
Producer stub artifact:     com.example:inventory-producer:2.3.0:stubs
Stub JAR SHA-256:           <digest-B>

Consumer source SHA:        <consumer-sha>
Stub Runner resolved:       inventory-producer:2.3.0:stubs
Consumer tests:             5 executed / 5 passed

Release decision:           eligible after required approvals/gates
~~~

Các giá trị trong dấu `<...>` là placeholder để CI điền. Spring Cloud Contract không tự tạo đủ metadata theo mẫu trên.

### Hai mô hình triển khai

**Contract JAR phát hành trước:** contract repo review và publish version bất biến, producer tải version đó và triển khai tới khi tests PASS, sau đó publish verified stubs.

**Candidate trước release:** CI tạo contract artifact tạm có ID duy nhất từ PR, producer/consumer thử trước; sau khi đạt và được review, mới công bố bản release.

Cả hai cần tuân thủ quy tắc **không phát hành verified stub khi producer tests chưa đạt**. Một candidate có thể được giữ trong CI/staging để debug nhưng không được mạo nhận là giao diện đã xác nhận.

### Những quality gates tối thiểu

- Resolver tải đúng contract artifact/SHA.
- Số contract được phát hiện khác 0 nếu module phải có contract.
- Generated producer tests thực sự chạy và PASS, không bị skip.
- Base test đúng test mode, fixture được dựng và code producer thật được gọi.
- Stub packaging và version/digest khớp với contract đã test.
- Consumer Stub Runner nạp đúng candidate producer stub.
- Consumer test kiểm tra request/response hoặc message handler thật.
- Breaking changes được review với consumer đang triển khai.
- Chỉ release job được cấp quyền mới có thể publish artifact verified.

## 21. Bài tập thực hành: JAR resolve được nhưng contract tests bằng 0

### Đề bài

Kho hợp đồng đã publish:

~~~text
com.example.contracts:shared-contracts:1.4.0

JAR entries:
  com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
~~~

Nhưng module Inventory producer dùng:

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractRepository {
        repositoryUrl =
            'https://repo.example.invalid/repository/contract-definitions'
    }

    // contractsPath chưa khai báo.
}
~~~

Build tải JAR thành công nhưng `0 generated contract tests`. Unit tests khác PASS.

**Câu hỏi 1. Nguyên nhân chính là gì?**

Plugin mặc định tìm path suy từ group/artifact của **contract dependency**, nhưng DSL của Inventory nằm dưới `com/example/inventory-producer`.

**Câu hỏi 2. Sửa thế nào?**

~~~groovy
contracts {
    contractsMode = 'REMOTE'

    contractDependency {
        stringNotation = 'com.example.contracts:shared-contracts:1.4.0'
    }

    contractRepository {
        repositoryUrl =
            'https://repo.example.invalid/repository/contract-definitions'
    }

    contractsPath = 'com/example/inventory-producer'
    failOnNoContracts = true
}
~~~

Cần có thêm plugin, base class, dependencies và task `contractTest` đúng project. `failOnNoContracts` là lớp bảo vệ, không thay thế việc xem test reports.

**Câu hỏi 3. Chuyển sang `contractsMode=LOCAL` có sửa được không?**

Không. Mode chỉ thay nguồn artifact, không sửa nested DSL path. LOCAL cũng yêu cầu JAR thực sự nằm trong Maven local repository của môi trường.

**Câu hỏi 4. Nếu producer test FAIL sau khi đọc đúng contract?**

Phải chặn phát hành stub, điều tra hợp đồng/implementation/fixture; không tự sửa DSL để che mismatch mà không hỏi consumer.

**Câu hỏi 5. Nếu consumer vẫn dùng stub version cũ?**

Kết quả consumer test chỉ chứng minh compatibility với stub cũ. Cần dùng **candidate producer `:stubs`** từ chính revision đã verify.

### Bài mở rộng: Git SCM

Repository Git chứa:

~~~text
META-INF/com.example/inventory-producer/2.3.0/contracts/
└── checkout-consumer/stockAvailable.groovy
~~~

Giải thích:

1. Vì sao cần tiền tố `git://` trước URL Git?
2. `contractDependency` dùng để định danh JAR hay tìm `group/artifact/version` trong SCM tree?
3. Có cần `pushStubsToScm` để **đọc** contract không?
4. Làm sao CI chứng minh contract commit nào đã được producer kiểm tra?
5. Vì sao có DSL nhưng chưa có folder `mappings` vẫn có thể hợp lý trước producer verification?

**Gợi ý:** `pushStubsToScm` dùng cho chiều **ghi** mappings sau kiểm chứng, không cần để đọc DSL.

### Câu hỏi tự kiểm tra

- `contractsDirectory` khác `contractsPath` ở đâu?
- `contractsDslDir` trong Gradle dùng khi nào?
- Contract JAR khác producer `:stubs` JAR ở trách nhiệm gì?
- `contractsMode=REMOTE` có tự chứng minh producer đúng contract không?
- Vì sao JAR chung cần folder producer và consumer?
- Làm sao xác định một build PASS nhưng không có generated tests?
- Tại sao Git version folder không tự pin commit?
- Khi nào nên dùng `LOCAL` và khi nào dùng `REMOTE`?
- Vì sao consumer test với stub cũ không xác nhận một PR mới?
- Khi nào pipeline được phép gọi `pushStubsToScm`?

## 22. Checklist trước khi chấp nhận thay đổi

- [ ] Biết rõ contract source: folder, Maven JAR hay Git SCM.
- [ ] Có owner/reviewer producer và consumer.
- [ ] DSL và fixtures được review, không có matcher quá lỏng làm mất tương thích.
- [ ] Với folder local, CI checkout đúng commit và path tồn tại.
- [ ] Với JAR, `contractDependency` đúng group/artifact/version và JAR có DSL entries thật.
- [ ] `contractsPath` trỏ đúng nested folder, không nhầm với đường dẫn máy dev.
- [ ] Với Git, URL có `git://` và đúng layout `META-INF/group/artifact/version/contracts`.
- [ ] `contractsMode` phù hợp LOCAL/REMOTE, credentials được cấp an toàn.
- [ ] Contract version bất biến hoặc candidate có ID/digest duy nhất.
- [ ] Build log ghi artifact/commit/digest đã resolve.
- [ ] Không vô tình loại hết contract bằng `includedFiles`/`ignoredFiles`.
- [ ] Generated tests được sinh, biên dịch, thực thi và **PASS**.
- [ ] Không bỏ qua test hoặc coi `0 tests` là thành công.
- [ ] Base class chạy đúng code producer trong phạm vi cần kiểm chứng.
- [ ] Producer `:stubs` được tạo từ đúng contract revision đã test.
- [ ] Không publish verified stub khi producer verification chưa đạt.
- [ ] `pushStubsToScm` nếu có được gate và chỉ job được cấp quyền thực thi.
- [ ] Consumer Stub Runner tải **producer stub**, không nhầm contract definitions JAR.
- [ ] Consumer HTTP client/message handler chạy thật với đúng stub candidate.
- [ ] Breaking changes được review cho các consumer đang triển khai.
- [ ] CI ghi contract SHA, producer SHA, artifact versions, digests và test reports.

## 23. Ghi nhớ và tài liệu tham khảo

**Lấy hợp đồng từ vị trí hoặc artifact ngoài dự án** chỉ thay đổi nơi producer nhận **nguồn DSL**. Với folder, dùng `contractsDirectory` (Maven) hoặc `contractsDslDir` (Gradle). Với JAR, dùng `contractDependency`, `contractsMode`, repository URL và `contractsPath`. Với Git SCM, dùng tiền tố `git://` và bố cục `META-INF/.../contracts` tương ứng.

Kho hợp đồng giúp consumer đề xuất/review yêu cầu, nhưng **producer vẫn phải sinh và chạy generated contract tests trên implementation thật**. Sau khi PASS, producer mới phát hành `:stubs`; consumer dùng Stub Runner với **đúng artifact version** để kiểm tra client/handler của mình.

### Tài liệu chính thức

- [Spring Cloud Contract — Common Repository with Contracts](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-common-repo-with-contracts.html): JAR dùng chung, layout theo producer/consumer và `contractsPath`.
- [Spring Cloud Contract — CDC with External Repository](https://docs.spring.io/spring-cloud-contract/reference/using/cdc-external-repo.html): cách consumer đề xuất và producer verify hợp đồng.
- [Spring Cloud Contract — Git as Storage](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-use-git-as-storage.html): tiền tố `git://`, SCM layout và `pushStubsToScm`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): `contractsDirectory`, `contractDependency`, `contractsMode`.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractsDslDir`, `contractRepository`, `contractsPath`, `contractTest`.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer sử dụng producer stub.
- [Maven — Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): Maven local/remote repositories.

**Kết luận thực hành:** khi CI báo PASS, hãy xác nhận **DSL đến từ đúng nguồn/version**, **producer test đã thực sự chạy và đạt**, và **consumer đang dùng verified stub từ chính producer revision đó**. Ba bằng chứng quan trọng hơn việc DSL nằm cạnh producer hay ở một repository hoàn toàn độc lập.
