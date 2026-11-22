# Methods Implementing an Interface Must Be Public in Java

An ordinary abstract instance method in a Java interface has **public** access, even when the declaration omits this keyword. Therefore, the class providing the body to satisfy that method must keep public access. Java does not allow an implementation to narrow the access level of the contract that the caller is using.

## 1. Correct and Incorrect Examples

Save the following program to **PublicContractDemo.java**:

~~~java
public class PublicContractDemo {
    interface Task {
        void run(); // Implicitly public abstract.
    }

    static final class PrintTask implements Task {
        @Override
        public void run() {
            System.out.println("running");
        }
    }

    public static void main(String[] args) {
        Task task = new PrintTask();
        task.run();
    }
}
~~~

Compile and run:

~~~bash
javac PublicContractDemo.java
java PublicContractDemo
~~~

Output:

~~~text
running
~~~

If you remove the **public** keyword from **PrintTask.run()**, the method in the class becomes package-private. The following snippet is intentionally written incorrectly:

~~~java
interface Task {
    void run();
}

class InvalidTask implements Task {
    @Override
    void run() {
        System.out.println("running");
    }
}
~~~

The compiler reports that the method in **InvalidTask** is attempting to implement a public method with weaker access privileges. Changing it to **protected** or **private** is also invalid. The **@Override** annotation helps verify the method relationship, but it does not automatically add the public keyword.

## 2. Why Must It Remain Public?

An interface is a type that calling code can depend on without needing to know the concrete implementing class. When a variable has type **Task**, the caller is permitted to call **run()** under the public contract. If an implementation could downgrade the method to package-private or protected, that same call would depend on the package or inheritance relationship of the concrete class, breaking the substitutability that the interface promises.

In a class, a method without a modifier defaults to package-private. Java does not automatically infer that you intend public just because the name and parameters match the interface. Therefore, explicitly write **public** when implementing an interface contract.

## 3. Distinguishing Method Types in an Interface

| Declaration form | Role | Does the implementing class need to write the method itself? |
| --- | --- | --- |
| Ordinary abstract method, for example **void run();** | Public abstract, no body | Yes, unless a valid implementation is already inherited; the body must be public |
| **default** method with a body | Default instance behavior, also public | Not required; if overridden, it must still be public |
| **static** method with a body | Belongs to the interface, called via the interface name | No; static methods do not override instance methods |
| **private** method with a body | Internal helper inside the interface | No; it is not a contract for the implementing class |

The **private** keyword in the table applies only to helpers with a body inside the interface. It does not allow a class to implement a public abstract method with a private method.

## 4. Can a Superclass Method Satisfy It?

A concrete class can satisfy an interface using a compatible, concrete, public method inherited from a superclass. It is not required to redeclare the method just to repeat the same body. However, a protected or package-private method from a superclass does not automatically become public when the subclass adds **implements**.

For example: if **BaseTask** has **public void run()**, the class **TaskImpl extends BaseTask implements Task** can use that method. If **BaseTask** only has **protected void run()**, the subclass must provide a valid public implementation or redesign the class relationship. The rules for inherited methods are analyzed separately in the next article of this chapter.

An abstract class must also follow this rule if it **redeclares** the interface method itself. It can leave the method undeclared and defer the obligation since it is still abstract, but it cannot write **protected abstract void run()** to replace a public interface method.

## 5. Common Mistakes

- Forgetting **public** under the assumption that Java will automatically inherit the modifier from the interface.
- Using **protected** on the grounds that only subclasses need to call the method. If it is a public method of the interface, keep it public and move the separate supporting logic into another protected/private helper.
- Assuming you must write every interface method yourself. A default method has a body, and a compatible public method from a superclass can also satisfy the contract.
- Confusing a **private** helper in an interface with an abstract method that the implementing class must provide.
- Looking only at the method name. Different parameter types still make a different signature; having the right public modifier with the wrong signature still fails to satisfy the contract.

## 6. Self-check

**Question 1.** Why does declaring **void save();** in an interface still require a public implementing method?

**Answer:** ordinary abstract instance methods in an interface are implicitly public abstract.

**Question 2.** Can an abstract class leave **save()** unimplemented?

**Answer:** yes, if the class remains abstract. However, if that class redeclares the method itself, it cannot narrow the access level of the public contract.

**Question 3.** If an interface has a public default method, can a subclass override it as protected?

**Answer:** no. When overriding, the method still cannot reduce the access level.

**Key takeaway:** the implementation body of a public interface instance method must be public. Distinguish between a method's modifier and whether the method needs to be written again.
