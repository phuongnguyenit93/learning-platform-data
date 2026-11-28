# Phân biệt annotation SDN, Spring Data Commons và annotation JPA

Khi ánh xạ mô hình Java vào Neo4j, một số annotation có tên giống annotation trong JPA hoặc Spring Data Commons. Chọn nhầm import có thể khiến Spring Data Neo4j không nhận ra metadata, bỏ qua cấu hình ánh xạ hoặc xử lý entity theo cách khác với dự định. Vì vậy, khi đọc một lớp entity, cần phân biệt **annotation mô tả cấu trúc đồ thị**, **annotation dùng chung của Spring Data** và **annotation dành cho mô hình quan hệ JPA**.

Trong module **SPRING_DATA_NEO4J**, mục tiêu là xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Bài này dùng mô hình phim–diễn viên với `Person`, `Movie` và relationship `ACTED_IN` để chỉ ra annotation nào thuộc Spring Data Neo4j (SDN), annotation nào thuộc Spring Data Commons và annotation nào chỉ dành cho JPA.

## 1. Ba nhóm annotation và trách nhiệm của chúng

| Nhóm | Vai trò | Ví dụ tiêu biểu |
|---|---|---|
| Spring Data Neo4j | Mô tả cấu trúc đồ thị và cách ánh xạ node, relationship, thuộc tính | `@Node`, `@Relationship`, `@RelationshipProperties`, `@TargetNode`, `@Property`, `@GeneratedValue` |
| Spring Data Commons | Metadata dùng chung cho nhiều module Spring Data như định danh, version, constructor và auditing | `@Id`, `@Version`, `@Transient`, `@PersistenceCreator`, `@CreatedDate` |
| JPA / Jakarta Persistence | Mô tả entity quan hệ, bảng, cột, khóa ngoại và liên kết giữa các bảng | `@Entity`, `@Table`, `@Column`, `@ManyToOne`, `@OneToMany`, `@JoinColumn` |

Hai nhóm đầu phối hợp để ánh xạ đối tượng Java vào Neo4j. Annotation JPA phục vụ mô hình lưu trữ quan hệ; chúng không thay thế annotation đồ thị của SDN.

## 2. Annotation chuyên biệt của Spring Data Neo4j

SDN dùng annotation trong package `org.springframework.data.neo4j.core.schema` để diễn tả cấu trúc node và relationship.

| Annotation | Ý nghĩa trong SDN |
|---|---|
| `@Node` | Đánh dấu lớp là mô hình node; có thể chỉ định label của node |
| `@Relationship` | Ánh xạ thuộc tính Java thành relationship, gồm type và direction |
| `@RelationshipProperties` | Đánh dấu lớp mô tả relationship có thuộc tính riêng |
| `@TargetNode` | Chỉ node ở đầu còn lại của relationship trong lớp relationship properties |
| `@RelationshipId` | Đánh dấu định danh nội bộ mà SDN dùng cho relationship được ánh xạ |
| `@Property` | Chỉ định tên property trong node hoặc relationship khi tên Java khác tên trong Neo4j |
| `@GeneratedValue` | Chỉ định cơ chế sinh giá trị định danh cho node khi dùng với `@Id` |
| `@DynamicLabels` | Ánh xạ tập label động của node khi mô hình cần quản lý label ngoài label chính |

Ví dụ, `Person` là node có quan hệ đi ra `ACTED_IN` tới `Movie`. Relationship chứa thuộc tính `roles`, vì vai diễn phụ thuộc vào cặp người–phim:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Direction;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Property("full_name")
    private String name;

    @Relationship(type = "ACTED_IN", direction = Direction.OUTGOING)
    private List<ActingCredit> actingCredits = new ArrayList<>();
}

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
    private Integer released;
}

@RelationshipProperties
public class ActingCredit {

    @RelationshipId
    private Long relationshipId;

    private List<String> roles;

    @TargetNode
    private Movie movie;
}
```

Các import trong ví dụ thể hiện một điểm dễ nhầm: `@Id` đến từ Spring Data Commons (`org.springframework.data.annotation.Id`), trong khi `@GeneratedValue`, `@Node` và các annotation mô tả relationship đến từ SDN. Không có `@Entity` JPA ở đây. `@Node("Person")` đã xác định đây là node có label `Person`.

`@Relationship` khai báo type `ACTED_IN` và hướng đi từ `Person` sang `Movie`. Lớp `ActingCredit` cho phép lưu `roles` trên relationship; `@TargetNode` trỏ tới node `Movie`. Nếu chỉ ánh xạ một danh sách `Movie` mà không có lớp relationship properties, ứng dụng sẽ không có trường Java tương ứng để biểu diễn thuộc tính `roles` của relationship.

`@RelationshipId` phục vụ việc SDN nhận diện relationship trong quá trình ánh xạ. Đây không phải khóa nghiệp vụ của credit và không nên dùng làm mã định danh công khai trong API. Tương tự, không nên mặc định internal ID do Neo4j quản lý là mã định danh nghiệp vụ ổn định. Nếu hệ thống cần mã có ý nghĩa hoặc được trao đổi với hệ thống khác, hãy thiết kế khóa nghiệp vụ hoặc UUID riêng.

## 3. Annotation dùng chung của Spring Data Commons

Spring Data Commons cung cấp metadata được tái sử dụng bởi nhiều module Spring Data. SDN hiểu và sử dụng một số annotation này khi ánh xạ node.

| Annotation | Package | Cách dùng với SDN |
|---|---|---|
| `@Id` | `org.springframework.data.annotation.Id` | Đánh dấu thuộc tính định danh của node |
| `@Version` | `org.springframework.data.annotation.Version` | Hỗ trợ optimistic locking để phát hiện cập nhật dựa trên phiên bản cũ |
| `@Transient` | `org.springframework.data.annotation.Transient` | Loại thuộc tính khỏi quá trình ánh xạ persistence |
| `@PersistenceCreator` | `org.springframework.data.annotation.PersistenceCreator` | Chỉ định constructor hoặc factory method được dùng khi tạo đối tượng từ dữ liệu |
| `@CreatedDate`, `@LastModifiedDate` | `org.springframework.data.annotation` | Lưu thời điểm tạo và cập nhật khi auditing được cấu hình |
| `@CreatedBy`, `@LastModifiedBy` | `org.springframework.data.annotation` | Lưu tác nhân tạo và cập nhật khi auditing và auditor provider được cấu hình |

### 3.1. @Id và @GeneratedValue

`@Id` đánh dấu trường định danh mà Spring Data sử dụng cho node. Trong SDN, annotation này là của Spring Data Commons. `@GeneratedValue` đi cùng nó khi muốn SDN sinh định danh theo generator được cấu hình:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
}
```

Đừng nhầm `@GeneratedValue` của SDN với `jakarta.persistence.GeneratedValue` của JPA. Chúng cùng tên nhưng thuộc hai cơ chế persistence khác nhau. Nếu dùng ID do ứng dụng cấp, cần cấu hình kiểu ID và generator phù hợp với phiên bản SDN đang sử dụng; không thêm annotation JPA chỉ để tạo khóa.

### 3.2. @Version cho optimistic locking

`@Version` là annotation Spring Data Commons. Với entity được hỗ trợ, SDN dùng thuộc tính version để kiểm soát cập nhật đồng thời. Khi một tiến trình cố ghi dựa trên phiên bản đã cũ, cơ chế optimistic locking có thể phát hiện xung đột thay vì âm thầm ghi đè thay đổi của tiến trình khác.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private String title;
}
```

Trường version do cơ chế persistence quản lý. Không nên tự tăng trường này trong logic nghiệp vụ. Cần kiểm tra hành vi xung đột và cách ứng dụng xử lý ngoại lệ trong kiểm thử tích hợp.

### 3.3. @Transient và constructor persistence

`@Transient` của Spring Data Commons đánh dấu thuộc tính không được lưu như một phần của entity. Ví dụ, `displayName` có thể được tính từ các thuộc tính khác:

```java
import org.springframework.data.annotation.Transient;

public class PersonView {

    private String name;

    @Transient
    private String displayName;
}
```

Ví dụ này chỉ minh họa ý nghĩa annotation; trong entity SDN, hãy đặt nó trên thuộc tính của lớp `@Node` tương ứng. `@PersistenceCreator` hữu ích khi lớp có nhiều constructor và cần chỉ rõ constructor mà Spring Data dùng để tạo đối tượng khi đọc dữ liệu. Các tham số constructor phải có thể được ánh xạ từ những thuộc tính mà persistence cung cấp.

Các annotation auditing như `@CreatedDate` hoặc `@LastModifiedDate` chỉ phát huy tác dụng khi auditing được bật và cấu hình đúng. Việc thêm annotation vào field không tự động tạo ra giá trị nếu ứng dụng chưa thiết lập cơ chế auditing.

## 4. Annotation JPA: dùng cho mô hình quan hệ

JPA (Jakarta Persistence) mô tả cách đối tượng Java ánh xạ sang bảng quan hệ. Một lớp JPA thường dùng `@Entity`, `@Table`, `@Column`, `@Id` và các annotation quan hệ như `@ManyToOne` hoặc `@OneToMany`.

Ví dụ dưới đây là mô hình JPA minh họa riêng cho cơ sở dữ liệu quan hệ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.List;

@Entity
@Table(name = "person")
public class PersonJpa {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "full_name")
    private String name;

    @OneToMany(mappedBy = "person")
    private List<ActingCreditJpa> actingCredits;
}
```

Trong JPA, `@OneToMany` mô tả liên kết giữa các entity quan hệ; `mappedBy` trỏ tới thuộc tính sở hữu quan hệ ở phía entity kia. Quan hệ đó được lưu bằng khóa ngoại hoặc bảng nối tùy mô hình. Trong Neo4j, liên kết giữa `Person` và `Movie` là relationship thực sự trong đồ thị, có type và hướng. SDN mô tả nó bằng `@Relationship`, còn thuộc tính của cạnh được mô hình hóa bằng `@RelationshipProperties`.

| Ý định mô hình hóa | Spring Data Neo4j | JPA |
|---|---|---|
| Khai báo một thực thể lưu trữ | `@Node` | `@Entity` |
| Đổi label hoặc tên property | `@Node("Person")`, `@Property("full_name")` | `@Table`, `@Column` |
| Định danh | Commons `@Id` và SDN `@GeneratedValue` khi cần | `jakarta.persistence.Id` và `jakarta.persistence.GeneratedValue` |
| Liên kết giữa hai thực thể | `@Relationship(type = "ACTED_IN")` | `@ManyToOne`, `@OneToMany`, `@ManyToMany`, `@OneToOne` |
| Thuộc tính của liên kết | `@RelationshipProperties`, `@TargetNode` | Entity liên kết hoặc cấu trúc quan hệ JPA phù hợp |
| Bỏ qua một thuộc tính | Commons `@Transient` | `jakarta.persistence.Transient` |

Không có phép thay thế một-một giữa mọi annotation của hai hệ. Chẳng hạn, `@Relationship` không chỉ là cách viết khác của `@OneToMany`: nó mô tả relationship có type và direction trong đồ thị. Cách tải dữ liệu, quản lý quan hệ và lưu thay đổi cũng tuân theo mô hình của từng store.

## 5. Những tên annotation dễ nhầm và import đúng

Một số annotation có cùng tên đơn giản nhưng khác package. Java phân biệt chúng theo tên đầy đủ, vì vậy IDE có thể tự thêm một import hợp lệ về cú pháp nhưng sai với persistence đang dùng.

| Tên ngắn | Import cần dùng trong entity SDN | Import dễ chọn nhầm |
|---|---|---|
| `@Id` | `org.springframework.data.annotation.Id` | `jakarta.persistence.Id` |
| `@GeneratedValue` | `org.springframework.data.neo4j.core.schema.GeneratedValue` | `jakarta.persistence.GeneratedValue` |
| `@Version` | `org.springframework.data.annotation.Version` | `jakarta.persistence.Version` |
| `@Transient` | `org.springframework.data.annotation.Transient` | `jakarta.persistence.Transient` |

Khi kiểm tra một lớp entity, hãy mở phần import và xác nhận package của từng annotation. Nếu có hai annotation trùng tên cần dùng trong cùng một file, Java không cho phép import đơn giản cả hai cùng tên; có thể dùng tên đầy đủ tại vị trí cần thiết hoặc tách mô hình persistence thành các lớp riêng để code dễ hiểu hơn.

## 6. Ví dụ sai thường gặp và cách sửa

### Sai: dùng entity JPA cho node Neo4j

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Movie {

    @Id
    private Long id;

    private String title;
}
```

Lớp trên được đánh dấu theo metadata JPA. SDN không dùng `@Entity` để nhận diện node và JPA `@Id` không phải annotation định danh mà SDN mong đợi.

### Đúng: dùng metadata SDN và Spring Data Commons

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
}
```

Lớp này được SDN nhận diện là node `Movie`; `@Id` là annotation Spring Data Commons và `@GeneratedValue` là annotation SDN. Các trường khác được ánh xạ thành property theo quy tắc mapping của SDN, trừ khi có metadata điều chỉnh.

### Sai: dùng quan hệ JPA để mô tả cạnh Neo4j

```java
@OneToMany(mappedBy = "person")
private List<Movie> movies;
```

`@OneToMany` không khai báo relationship type `ACTED_IN` hoặc hướng của cạnh trong Neo4j. Hãy dùng metadata SDN:

```java
@Relationship(type = "ACTED_IN", direction = Direction.OUTGOING)
private List<Movie> movies;
```

Nếu cạnh có thuộc tính `roles`, thay `List<Movie>` bằng danh sách lớp được đánh dấu `@RelationshipProperties`, trong đó có `@TargetNode Movie` và trường `roles`.

## 7. Khi ứng dụng dùng cả Neo4j và cơ sở dữ liệu quan hệ

Một ứng dụng Spring có thể cần cả Neo4j và một cơ sở dữ liệu quan hệ. Trong trường hợp đó, mỗi store có repository, cấu hình và metadata mapping tương ứng. Ví dụ, `PersonGraph` có thể là `@Node` dùng với `Neo4jRepository`, trong khi `PersonRecord` là `@Entity` dùng với JPA repository.

Tách các lớp persistence theo store thường làm rõ trách nhiệm và tránh nhầm annotation, repository hoặc quy tắc quan hệ. Nếu chủ động dùng chung một lớp cho nhiều store, cần cấu hình repository scanning và mapping thật rõ ràng, sau đó kiểm thử việc đọc/ghi của từng store. Không nên thêm đồng thời `@Node` và `@Entity` chỉ để thử xem framework nào nhận lớp đó.

`@Transactional` cũng cần được hiểu theo cấu hình transaction của ứng dụng. Annotation này thuộc Spring Framework, không phải annotation JPA hay SDN schema. Khi có nhiều transaction manager, cần chỉ rõ transaction manager phù hợp cho nghiệp vụ Neo4j hoặc JPA để tránh một phương thức vô tình tham gia sai transaction.

## 8. Checklist trước khi hoàn thiện entity SDN

- Lớp node được đánh dấu bằng `@Node` và label đúng với mô hình đồ thị.
- Trường định danh dùng `org.springframework.data.annotation.Id`; generator, nếu cần, dùng annotation SDN.
- Thuộc tính node dùng quy tắc property của SDN; dùng `@Property` khi cần đổi tên key.
- Quan hệ được khai báo bằng `@Relationship` với type và direction rõ ràng.
- Relationship có thuộc tính riêng được mô tả bằng `@RelationshipProperties` và `@TargetNode`.
- Annotation Commons như `@Version`, `@Transient` hoặc auditing được import đúng package và chỉ dùng khi có nhu cầu.
- Không dùng annotation JPA như `@Entity`, `@Column`, `@ManyToOne` hoặc `@JoinColumn` để mô tả mapping Neo4j.
- Nếu dự án có cả hai store, repository và transaction manager được cấu hình tách bạch, có kiểm thử tích hợp cho từng store.

## 9. Bài tập tự kiểm tra

1. Vì sao entity SDN dùng `org.springframework.data.annotation.Id` thay vì `jakarta.persistence.Id`?
2. `@Node` và `@Entity` khác nhau ở mục đích nào?
3. Khi nào cần `@RelationshipProperties` thay vì chỉ khai báo `List<Movie>` trên `Person`?
4. Annotation nào chỉ định node ở đầu còn lại của relationship?
5. `@Version` thuộc Spring Data Commons hay JPA? SDN dùng nó để giải quyết vấn đề gì?
6. Vì sao `@OneToMany` không thể thay thế `@Relationship(type = "ACTED_IN")`?
7. Nếu ứng dụng dùng đồng thời Neo4j và PostgreSQL, vì sao nên tách rõ model và repository cho từng store?

Khi trả lời được các câu hỏi này và kiểm tra được package import trong mã nguồn, bạn sẽ tránh được phần lớn lỗi do trộn metadata giữa SDN, Spring Data Commons và JPA. Việc chọn đúng annotation giúp mô hình Java phản ánh đúng node và relationship trong Neo4j, đồng thời giữ tầng dữ liệu nhất quán với mục tiêu của Spring Data Neo4j.
