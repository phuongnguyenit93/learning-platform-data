# Ánh xạ nhiều-nhiều bằng @ManyToMany và @JoinTable

Quan hệ nhiều-nhiều (many-to-many) xuất hiện khi một bản ghi của Entity này có thể liên kết với nhiều bản ghi của Entity kia, đồng thời mỗi bản ghi ở phía bên kia cũng có thể liên kết với nhiều bản ghi ở phía đầu tiên. Ví dụ, một bài viết có nhiều thẻ (tag), và một thẻ có thể được dùng cho nhiều bài viết.

Trong JPA, quan hệ này thường được ánh xạ bằng @ManyToMany. Hai bảng Entity được nối qua một **bảng trung gian (join table)**; @JoinTable cho phép khai báo tên bảng trung gian, cột khóa ngoại trỏ đến Entity sở hữu và cột khóa ngoại trỏ đến Entity còn lại.

Điểm quan trọng nhất khi thiết kế là xác định **phía sở hữu quan hệ (owning side)**. Phía này điều khiển việc ghi thay đổi quan hệ xuống bảng trung gian. Nếu ánh xạ hai chiều, phía còn lại dùng mappedBy để trỏ về thuộc tính của phía sở hữu.

## 1. Quan hệ nhiều-nhiều là gì?

Ví dụ hệ thống quản lý bài viết và thẻ:

- Một Post có thể có nhiều Tag.
- Một Tag có thể xuất hiện trong nhiều Post.
- Một Post có thể không có Tag nào.
- Một Tag có thể chưa được gắn vào Post nào.

Sơ đồ quan hệ:

~~~text
POST                         TAG
-----                        -----
id (PK)                      id (PK)
title                        name
   |                            |
   |                            |
   +--------- POST_TAG ---------+
             post_id (FK)
             tag_id  (FK)
~~~

Bảng POST_TAG lưu các cặp liên kết. Ví dụ:

| post_id | tag_id |
|---:|---:|
| 10 | 1 |
| 10 | 2 |
| 11 | 1 |

Post 10 có hai Tag (1 và 2). Tag 1 được dùng trong cả Post 10 và Post 11.

Về mặt quan hệ trong database, đây là hai quan hệ một-nhiều đi qua bảng trung gian:

- POST 1 - N POST_TAG.
- TAG 1 - N POST_TAG.

JPA có thể che giấu bảng trung gian ở mô hình object bằng @ManyToMany, nhưng bảng đó vẫn tồn tại trong schema.

## 2. Ánh xạ một chiều với @ManyToMany và @JoinTable

Nếu chỉ cần truy cập từ Post đến Tag, có thể ánh xạ một chiều:

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "post_tags",
        joinColumns = @JoinColumn(name = "post_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private List<Tag> tags = new ArrayList<>();

    protected Post() {
    }

    public Post(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public List<Tag> getTags() {
        return tags;
    }
}
~~~

Entity Tag:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "tags")
public class Tag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    protected Tag() {
    }

    public Tag(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Trong @JoinTable:

- name = "post_tags" là tên bảng trung gian.
- joinColumns mô tả cột khóa ngoại trỏ đến Entity sở hữu quan hệ, ở đây là Post.
- inverseJoinColumns mô tả cột khóa ngoại trỏ đến Entity còn lại, ở đây là Tag.
- @JoinColumn(name = "post_id") đặt tên cột lưu khóa của Post.
- @JoinColumn(name = "tag_id") đặt tên cột lưu khóa của Tag.

Ở ví dụ này, Post là owning side vì @JoinTable được khai báo trên thuộc tính tags của Post. Tag không cần biết danh sách Post nếu ứng dụng chỉ cần điều hướng một chiều.

Một chiều phù hợp khi thao tác nghiệp vụ chủ yếu bắt đầu từ một phía và không cần truy cập ngược từ Tag về Post. Không cần khai báo hai chiều chỉ vì database có thể truy vấn theo cả hai hướng; có thể viết query riêng nếu nhu cầu chỉ là tra cứu ngược.

## 3. Ánh xạ hai chiều và mappedBy

Khi ứng dụng cần truy cập cả Post.tags và Tag.posts, có thể ánh xạ hai chiều.

Phía sở hữu Post:

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "post_tags",
        joinColumns = @JoinColumn(name = "post_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private List<Tag> tags = new ArrayList<>();

    protected Post() {
    }

    public Post(String title) {
        this.title = title;
    }

    public void addTag(Tag tag) {
        if (!tags.contains(tag)) {
            tags.add(tag);
            tag.addPostFromPost(this);
        }
    }

    public void removeTag(Tag tag) {
        if (tags.remove(tag)) {
            tag.removePostFromPost(this);
        }
    }

    public List<Tag> getTags() {
        return tags;
    }
}
~~~

Phía nghịch đảo Tag:

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "tags")
public class Tag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @ManyToMany(mappedBy = "tags", fetch = FetchType.LAZY)
    private List<Post> posts = new ArrayList<>();

    protected Tag() {
    }

    public Tag(String name) {
        this.name = name;
    }

    void addPostFromPost(Post post) {
        if (!posts.contains(post)) {
            posts.add(post);
        }
    }

    void removePostFromPost(Post post) {
        posts.remove(post);
    }

    public List<Post> getPosts() {
        return posts;
    }
}
~~~

Giải thích mappedBy:

~~~java
@ManyToMany(mappedBy = "tags")
private List<Post> posts;
~~~

Giá trị "tags" là **tên thuộc tính Java** trong Entity Post, nơi khai báo @JoinTable. Nó không phải tên bảng post_tags và cũng không phải tên cột tag_id.

Trong quan hệ hai chiều:

- Post là owning side vì có @JoinTable.
- Tag là inverse side vì có mappedBy.
- Chỉ thay đổi collection ở inverse side có thể không làm thay đổi bảng trung gian.
- Khi thêm hoặc xóa liên kết, nên đồng bộ cả hai collection trong bộ nhớ.

Các phương thức addTag và removeTag giúp cập nhật cả hai phía. Chúng không tự lưu dữ liệu; Entity vẫn phải được persist hoặc thay đổi trong transaction phù hợp.

## 4. Owning side quyết định việc ghi quan hệ

Đây là quy tắc quan trọng nhất của quan hệ hai chiều JPA.

Giả sử Post có:

~~~java
@ManyToMany
@JoinTable(name = "post_tags", ...)
private List<Tag> tags;
~~~

và Tag có:

~~~java
@ManyToMany(mappedBy = "tags")
private List<Post> posts;
~~~

Nếu chỉ gọi:

~~~java
tag.getPosts().add(post);
~~~

thì bạn chỉ thay đổi collection ở inverse side. JPA dựa vào owning side để ghi quan hệ; vì vậy, thay đổi này có thể không được lưu vào post_tags.

Hãy gọi helper ở owning side:

~~~java
post.addTag(tag);
~~~

Phương thức này cập nhật Post.tags và Tag.posts. Khi transaction được flush, provider sẽ đồng bộ liên kết theo trạng thái của owning side.

Nếu không có helper, có thể cập nhật trực tiếp cả hai collection, nhưng cần bảo đảm không bỏ sót một phía. Tránh để controller hoặc nhiều service tự thao tác collection theo các quy tắc khác nhau.

## 5. Schema của bảng trung gian

Với hai bảng Post và Tag dùng khóa Long, một schema SQL điển hình:

~~~sql
CREATE TABLE posts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE tags (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE post_tags (
    post_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (post_id, tag_id),
    CONSTRAINT fk_post_tags_post
        FOREIGN KEY (post_id) REFERENCES posts(id),
    CONSTRAINT fk_post_tags_tag
        FOREIGN KEY (tag_id) REFERENCES tags(id)
);
~~~

Cú pháp identity có thể cần điều chỉnh theo database. Ví dụ này minh họa cấu trúc quan hệ: hai khóa ngoại và khóa chính ghép trên cặp (post_id, tag_id).

Khóa chính ghép hoặc unique constraint trên cặp hai cột giúp ngăn một Post được liên kết lặp với cùng một Tag ở mức database. Đây là lớp bảo vệ hữu ích kể cả khi code ứng dụng có lỗi.

Nếu cần tên constraint hoặc index cụ thể, có thể tạo chúng bằng migration Flyway/Liquibase thay vì phụ thuộc hoàn toàn vào DDL tự sinh của Hibernate. Ví dụ index theo tag_id có thể hữu ích khi thường xuyên tìm tất cả Post của một Tag.

## 6. Thêm và xóa liên kết trong transaction

Thông thường, Tag là dữ liệu dùng chung. Trước khi gắn một Tag vào Post, hãy tải Tag đang được quản lý bởi persistence context hoặc tạo Tag mới theo đúng nghiệp vụ.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PostService {

    private final PostRepository postRepository;
    private final TagRepository tagRepository;

    public PostService(
            PostRepository postRepository,
            TagRepository tagRepository) {
        this.postRepository = postRepository;
        this.tagRepository = tagRepository;
    }

    @Transactional
    public void addExistingTag(Long postId, Long tagId) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Post not found"));

        Tag tag = tagRepository.findById(tagId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Tag not found"));

        post.addTag(tag);
    }

    @Transactional
    public void removeTag(Long postId, Long tagId) {
        Post post = postRepository.findById(postId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Post not found"));

        Tag tag = tagRepository.findById(tagId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Tag not found"));

        post.removeTag(tag);
    }
}
~~~

Nếu các Entity đang được quản lý trong cùng transaction, dirty checking có thể ghi thay đổi join table khi transaction commit. Không nhất thiết phải gọi save() lại cho mọi Entity đã managed, dù có thể gọi save nếu quy ước dự án yêu cầu.

Để tạo Post và Tag mới, có thể persist cả hai theo thứ tự phù hợp, rồi thêm liên kết. Mặc định @ManyToMany không khai báo cascade. Nếu không dùng cascade PERSIST, hãy lưu Tag và Post rõ ràng trước khi thiết lập liên kết.

## 7. Cascade trong quan hệ nhiều-nhiều

Cascade cho phép thao tác trên Entity này lan sang Entity liên quan. Tuy nhiên, trong nhiều-nhiều, một Entity thường được chia sẻ bởi nhiều Entity khác.

Ví dụ Tag "java" có thể được dùng bởi hàng nghìn Post. Nếu Post khai báo:

~~~java
@ManyToMany(cascade = CascadeType.ALL)
private List<Tag> tags;
~~~

CascadeType.ALL bao gồm REMOVE. Xóa một Post có thể lan thao tác xóa sang Tag được chia sẻ, dẫn đến mất dữ liệu mà các Post khác vẫn đang sử dụng hoặc vi phạm ràng buộc khóa ngoại.

Nguyên tắc thực tế:

- Không cascade REMOVE hoặc ALL cho Entity dùng chung như Tag nếu không có mô hình vòng đời đặc biệt.
- Cascade PERSIST hoặc MERGE chỉ khi việc tạo/cập nhật Entity liên quan thực sự thuộc trách nhiệm của Entity gốc.
- Nếu Tag được quản lý độc lập, thường nên lưu và xóa Tag qua TagRepository/service riêng.
- Xóa một liên kết Post-Tag phải xóa hàng tương ứng trong bảng post_tags, không xóa bản ghi Tag.

@OneToMany có orphanRemoval, nhưng @ManyToMany không có thuộc tính orphanRemoval. Việc bỏ một phần tử khỏi collection nhiều-nhiều nhằm xóa liên kết, không tự động xóa Entity ở đầu kia.

## 8. Fetching và chi phí truy vấn

@ManyToMany có fetch mặc định là LAZY. Nên ghi rõ:

~~~java
@ManyToMany(fetch = FetchType.LAZY)
private List<Tag> tags = new ArrayList<>();
~~~

LAZY giúp trì hoãn việc tải collection cho đến khi được truy cập, nhưng đây là yêu cầu/hint mà provider phải xử lý theo hợp đồng JPA. Không nên giả định mọi thao tác đều chỉ tạo một câu SQL.

Ví dụ N+1:

~~~java
List<Post> posts = postRepository.findAll();

for (Post post : posts) {
    System.out.println(post.getTags().size());
}
~~~

Nếu collection chưa được tải, việc truy cập tags cho từng Post có thể gây thêm một truy vấn cho mỗi Post. Với nhiều Post, số lượng truy vấn tăng nhanh.

Có thể dùng fetch join cho một truy vấn cần dữ liệu liên quan:

~~~java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PostRepository
        extends JpaRepository<Post, Long> {

    @Query("""
        select distinct p
        from Post p
        left join fetch p.tags
        where p.id = :id
        """)
    Optional<Post> findByIdWithTags(@Param("id") Long id);
}
~~~

distinct giúp loại kết quả Post lặp ở cấp Entity khi join tạo nhiều dòng cho một Post. Fetch join collection cần cẩn thận với phân trang: kết hợp phân trang và collection fetch join có thể làm kết quả phân trang không đúng kỳ vọng hoặc khiến provider phải tải nhiều dữ liệu rồi phân trang trong bộ nhớ. Với danh sách phân trang, cân nhắc truy vấn ID trước rồi tải quan hệ cho tập ID đó, hoặc dùng projection phù hợp.

Không nên đặt EAGER chỉ để che lỗi LazyInitializationException. Hãy xác định use case cần dữ liệu gì, tải trong transaction phù hợp và dùng projection/entity graph/fetch join có kiểm soát.

## 9. Khi bảng trung gian có thuộc tính riêng

@ManyToMany chỉ phù hợp khi bảng liên kết chứa các khóa ngoại và không có dữ liệu nghiệp vụ riêng. Nếu quan hệ có thêm thuộc tính như:

- thời điểm Post được gắn Tag,
- người thực hiện thao tác,
- thứ tự hiển thị,
- trạng thái duyệt,
- nguồn gắn thẻ hoặc ghi chú,

thì bảng trung gian đã trở thành một Entity có ý nghĩa nghiệp vụ. Khi đó, nên thay @ManyToMany bằng Entity liên kết, ví dụ PostTag, với hai quan hệ @ManyToOne.

Ví dụ:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "post_tags",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"post_id", "tag_id"}
    )
)
public class PostTag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "tag_id", nullable = false)
    private Tag tag;

    @Column(nullable = false)
    private Instant addedAt;

    protected PostTag() {
    }

    public PostTag(Post post, Tag tag, Instant addedAt) {
        this.post = post;
        this.tag = tag;
        this.addedAt = addedAt;
    }
}
~~~

Lúc này, có thể thêm Repository riêng cho PostTag và truy vấn các thuộc tính của quan hệ trực tiếp. Mô hình rõ ràng hơn khi liên kết có vòng đời, validation hoặc dữ liệu riêng.

## 10. Đồng bộ collection hai chiều và serialization

Trong quan hệ hai chiều, helper methods nên giữ hai collection đồng bộ. Tuy nhiên, trả Entity trực tiếp từ REST API có thể gây vòng lặp JSON:

~~~text
Post -> tags -> posts -> tags -> ...
~~~

Tránh serialize trực tiếp cả hai phía. Thay vào đó:

- Dùng DTO hoặc projection cho response.
- Chọn rõ trường cần trả về.
- Có thể dùng annotation Jackson để quản lý quan hệ hai chiều nếu dự án chọn cách đó, nhưng DTO thường dễ kiểm soát hợp đồng API hơn.
- Không để getter collection vô tình kích hoạt lazy loading ngoài transaction.

Nếu dùng Lombok, tránh @Data trên Entity có quan hệ hai chiều vì equals(), hashCode() và toString() được sinh tự động có thể đi qua collection, gây đệ quy, tải dữ liệu hoặc so sánh không ổn định.

## 11. Các lỗi thường gặp

**Chỉ cập nhật collection ở phía mappedBy**

Thay đổi inverse side có thể không được ghi vào join table. Hãy cập nhật owning side và đồng bộ cả hai collection bằng helper method.

**Đặt @JoinTable ở cả hai phía**

Trong ánh xạ hai chiều, chỉ owning side khai báo @JoinTable. Phía còn lại dùng mappedBy trỏ đến thuộc tính Java của owning side.

**Dùng CascadeType.ALL cho Entity dùng chung**

Có nguy cơ cascade REMOVE làm xóa Tag được chia sẻ. Xóa liên kết thay vì xóa Entity liên quan.

**Dùng @ManyToMany khi join table có dữ liệu riêng**

Khi liên kết có ngày tạo, thứ tự hoặc trạng thái, hãy mô hình hóa bảng liên kết thành Entity riêng với hai @ManyToOne.

**Tải collection lớn trong danh sách**

Có thể gây N+1 hoặc trả về quá nhiều dữ liệu. Dùng projection, phân trang và fetch có chủ đích.

**Gọi getter lazy sau khi transaction kết thúc**

Có thể gây LazyInitializationException. Tải dữ liệu trong transaction hoặc thiết kế truy vấn trả đúng dữ liệu cần thiết.

**Không kiểm soát duplicate association**

Dùng unique constraint hoặc primary key ghép trên cặp khóa ngoại của join table. Đồng thời kiểm tra collection trước khi thêm liên kết.

## 12. Quy trình kiểm tra mapping nhiều-nhiều

Khi triển khai quan hệ mới, hãy kiểm tra:

1. Mô hình nghiệp vụ có thật sự là nhiều-nhiều hay quan hệ cần Entity liên kết riêng?
2. Bảng trung gian có tên rõ ràng, hai khóa ngoại và ràng buộc duy nhất trên cặp khóa hay không?
3. Đã xác định đúng owning side và mappedBy hay chưa?
4. Helper methods có cập nhật cả hai phía không?
5. Cascade có phù hợp với vòng đời của Entity dùng chung không?
6. Collection có fetch LAZY và truy vấn có kiểm soát tải quan hệ không?
7. Truy vấn phân trang có tránh collection fetch join không phù hợp không?
8. Serialization có tránh vòng lặp và lazy loading ngoài ý muốn không?
9. Integration test có kiểm tra thêm, xóa và đọc lại liên kết từ database không?

## 13. Kết luận

@ManyToMany và @JoinTable giúp ánh xạ quan hệ nhiều-nhiều thông qua bảng trung gian. Khi ánh xạ hai chiều, owning side quyết định việc ghi quan hệ; inverse side dùng mappedBy và nên được đồng bộ trong helper methods. Với Entity dùng chung như Tag, cần thận trọng với cascade REMOVE. Khi join table có thuộc tính nghiệp vụ, hãy chuyển nó thành Entity liên kết với hai quan hệ @ManyToOne. Fetching cần được thiết kế theo use case để tránh N+1, tải quá nhiều dữ liệu và lỗi lazy loading.
